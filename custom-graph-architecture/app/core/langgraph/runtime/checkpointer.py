"""Postgres checkpointer — the graph's short-term memory.

The checkpointer persists ``GraphState`` after every node, which is what makes the two
``interrupt()`` gates in the spec work: ``wait_for_user`` and ``hitl_review`` suspend the
graph, the state survives in Postgres, and the next request resumes it with
``Command(resume=...)``.

Owns its own psycopg pool. The ORM engine in ``app/services/database.py`` cannot be reused:
``AsyncPostgresSaver`` requires ``autocommit=True``, no prepared-statement caching, and
``dict_row`` rows.
"""

import asyncio

from langgraph.checkpoint.postgres.aio import AsyncPostgresSaver
from psycopg.rows import dict_row
from psycopg_pool import AsyncConnectionPool

from app.core.configs.config import settings
from app.core.logging import logger

_CONNECTION_KWARGS = {
    "autocommit": True,
    "prepare_threshold": None,
    "row_factory": dict_row,
}


class CheckpointerResource:
    """Lazily opens the checkpointer pool and runs the one-time table setup.

    ``setup()`` is idempotent but not free, so it runs once per process at graph creation
    rather than per request. The pool is opened with ``open=False`` followed by an explicit
    ``await pool.open()`` so it binds to the running event loop instead of whichever loop
    happened to be current at import time.
    """

    def __init__(self) -> None:
        self._pool: AsyncConnectionPool | None = None
        self._checkpointer: AsyncPostgresSaver | None = None
        self._lock = asyncio.Lock()

    async def get(self) -> AsyncPostgresSaver:
        """Return the process-wide checkpointer, initialising it on first call.

        Returns:
            AsyncPostgresSaver: A checkpointer whose tables exist and are migrated.

        Raises:
            psycopg.OperationalError: If Postgres is unreachable.
        """
        if self._checkpointer is not None:
            return self._checkpointer

        async with self._lock:
            # A second caller may have finished initialisation while this one waited.
            if self._checkpointer is not None:
                return self._checkpointer

            pool = AsyncConnectionPool(
                conninfo=settings.psycopg_database_uri,
                min_size=1,
                max_size=settings.POSTGRES_POOL_SIZE,
                open=False,
                kwargs=_CONNECTION_KWARGS,
            )
            await pool.open()

            checkpointer = AsyncPostgresSaver(pool)
            await checkpointer.setup()

            self._pool = pool
            self._checkpointer = checkpointer
            logger.info("checkpointer_ready", max_size=settings.POSTGRES_POOL_SIZE)
            return checkpointer

    async def close(self) -> None:
        """Close the pool at shutdown."""
        if self._pool is None:
            return
        await self._pool.close()
        self._pool = None
        self._checkpointer = None
        logger.info("checkpointer_closed")


checkpointer_resource = CheckpointerResource()
