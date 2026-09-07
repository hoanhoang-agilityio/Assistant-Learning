"""SQLAlchemy async engine and session factory for the application's own tables.

This is one of the two Postgres pools in the project, and it is deliberately not shared
with the other: the LangGraph checkpointer (``src/runtime/backends/postgres.py``) opens a
raw ``psycopg_pool.AsyncConnectionPool`` because it needs autocommit and dict rows, neither
of which the ORM wants.
"""

from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from src.configs.config import settings

engine: AsyncEngine = create_async_engine(
    settings.sqlalchemy_database_uri,
    pool_size=settings.POSTGRES_POOL_SIZE,
    max_overflow=settings.POSTGRES_MAX_OVERFLOW,
    pool_pre_ping=True,
    echo=False,
)

session_factory: async_sessionmaker[AsyncSession] = async_sessionmaker(
    engine,
    class_=AsyncSession,
    expire_on_commit=False,
)


async def close_engine() -> None:
    """Dispose the engine's connection pool at shutdown."""
    await engine.dispose()
