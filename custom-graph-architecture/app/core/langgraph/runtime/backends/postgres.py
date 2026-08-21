"""Postgres implementation of ``GraphRuntime``.

One psycopg pool, two consumers: ``AsyncPostgresSaver`` and ``AsyncPostgresStore`` take the
same connection type and the same connection settings, so opening a second pool would only
double the connection count.

The SQLAlchemy engine in ``app/services/database.py`` stays separate — it is the ORM's, and
these two need ``autocommit=True``, no prepared-statement caching, and ``dict_row``.
"""

import asyncio

from langgraph.checkpoint.postgres.aio import AsyncPostgresSaver
from langgraph.store.postgres.aio import AsyncPostgresStore
from psycopg.rows import dict_row
from psycopg_pool import AsyncConnectionPool

from app.core.configs.config import settings
from app.core.langgraph.runtime.base import GraphRuntime
from app.core.logging import logger

_CONNECTION_KWARGS = {
    "autocommit": True,
    "prepare_threshold": None,
    "row_factory": dict_row,
}


class PostgresRuntime(GraphRuntime):
    """Lazily opens the shared pool and runs each backend's one-time table setup.

    ``setup()`` is idempotent but not free, so it runs once per process on first use rather
    than per request. The pool is created with ``open=False`` followed by an explicit
    ``await pool.open()`` so it binds to the running event loop instead of whichever loop
    happened to be current at import time.
    """

    def __init__(self) -> None:
        self._pool: AsyncConnectionPool | None = None
        self._checkpointer: AsyncPostgresSaver | None = None
        self._store: AsyncPostgresStore | None = None
        self._lock = asyncio.Lock()

    async def _get_pool(self) -> AsyncConnectionPool:
        """Return the shared pool, opening it on first use.

        Returns:
            AsyncConnectionPool: An open pool configured for LangGraph's Postgres backends.
        """
        if self._pool is None:
            self._pool = AsyncConnectionPool(
                conninfo=settings.psycopg_database_uri,
                min_size=1,
                max_size=settings.POSTGRES_POOL_SIZE,
                open=False,
                kwargs=_CONNECTION_KWARGS,
            )
            await self._pool.open()
            logger.info("postgres_pool_opened", max_size=settings.POSTGRES_POOL_SIZE)
        return self._pool

    async def checkpointer(self) -> AsyncPostgresSaver:
        """Return the process-wide checkpointer, migrating its tables on first call.

        Returns:
            AsyncPostgresSaver: Short-term memory for the graph, keyed by ``thread_id``.

        Raises:
            psycopg.OperationalError: If Postgres is unreachable.
        """
        if self._checkpointer is not None:
            return self._checkpointer

        async with self._lock:
            # A second caller may have finished initialisation while this one waited.
            if self._checkpointer is None:
                checkpointer = AsyncPostgresSaver(await self._get_pool())
                await checkpointer.setup()
                self._checkpointer = checkpointer
                logger.info("checkpointer_ready", backend="postgres")
        return self._checkpointer

    async def store(self) -> AsyncPostgresStore:
        """Return the process-wide long-term store, migrating its tables on first call.

        Returns:
            AsyncPostgresStore: Long-term memory, addressed by namespace.

        Raises:
            psycopg.OperationalError: If Postgres is unreachable.
        """
        if self._store is not None:
            return self._store

        async with self._lock:
            if self._store is None:
                store = AsyncPostgresStore(await self._get_pool())
                await store.setup()
                self._store = store
                logger.info("store_ready", backend="postgres")
        return self._store

    async def close(self) -> None:
        """Close the shared pool at shutdown."""
        if self._pool is None:
            return
        await self._pool.close()
        self._pool = None
        self._checkpointer = None
        self._store = None
        logger.info("postgres_pool_closed")
