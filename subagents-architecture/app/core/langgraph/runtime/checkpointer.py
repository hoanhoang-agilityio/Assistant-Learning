"""Ownership of the Postgres resources used by LangGraph checkpoints."""

from langgraph.checkpoint.postgres.aio import AsyncPostgresSaver
from psycopg.rows import dict_row
from psycopg_pool import AsyncConnectionPool

from app.core.configs.config import Environment, settings


class CheckpointerResources:
    """Open and retain the connection pool and checkpointer for one process."""

    def __init__(self) -> None:
        """Prepare lazily-created checkpoint resources."""
        self.connection_pool: AsyncConnectionPool | None = None
        self.checkpointer: AsyncPostgresSaver | None = None

    async def get_connection_pool(self) -> AsyncConnectionPool | None:
        """Open the psycopg pool once, degrading only in production.

        Returns:
            The open pool, or ``None`` in production when Postgres is
            unreachable.

        Raises:
            Exception: Propagated outside production.
        """
        if self.connection_pool is not None:
            return self.connection_pool
        try:
            pool = AsyncConnectionPool(
                settings.checkpointer_database_uri,
                open=False,
                max_size=settings.POSTGRES_POOL_SIZE,
                kwargs={
                    "autocommit": True,
                    "prepare_threshold": None,
                    "row_factory": dict_row,
                },
            )
            await pool.open()
            self.connection_pool = pool
            return pool
        except Exception:
            if settings.ENVIRONMENT == Environment.PRODUCTION:
                return None
            raise

    async def get_checkpointer(self) -> AsyncPostgresSaver | None:
        """Build and set up the Postgres saver once.

        Returns:
            The saver, or ``None`` when its pool is unavailable in production.

        Raises:
            RuntimeError: When the pool is unavailable outside production.
        """
        if self.checkpointer is not None:
            return self.checkpointer
        connection_pool = await self.get_connection_pool()
        if connection_pool is None:
            if settings.ENVIRONMENT == Environment.PRODUCTION:
                return None
            raise RuntimeError("checkpointer pool unavailable outside production")
        checkpointer = AsyncPostgresSaver(connection_pool)
        await checkpointer.setup()
        self.checkpointer = checkpointer
        return checkpointer

    async def clear_thread(self, session_id: str) -> None:
        """Delete every checkpoint row for one thread.

        Args:
            session_id: Session id used as the checkpointer ``thread_id``.

        Raises:
            RuntimeError: When no checkpointer pool is available.
        """
        pool = await self.get_connection_pool()
        if pool is None:
            raise RuntimeError("cannot clear history — checkpointer is unavailable")
        async with pool.connection() as connection, connection.pipeline():
            for table in settings.CHECKPOINT_TABLES:
                await connection.execute(
                    f"DELETE FROM {table} WHERE thread_id = %s",
                    (session_id,),
                )


__all__ = ["CheckpointerResources"]
