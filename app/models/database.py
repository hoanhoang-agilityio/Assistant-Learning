"""SQLAlchemy engine for the auth tables.

Separate from the LangGraph checkpointer's psycopg connection pool: that pool is
tuned for long-running graph writes, while this engine serves short
authentication reads.
"""

from sqlalchemy import Engine
from sqlmodel import create_engine

from app.core.configs.config import settings

_uri = settings.sqlalchemy_database_uri

# SQLite (used by tests and smoke runs) has no server-side pool to size, and
# passing pool arguments to its driver raises.
_pool_kwargs: dict[str, object] = (
    {}
    if _uri.startswith("sqlite")
    else {
        "pool_size": settings.POSTGRES_POOL_SIZE,
        "max_overflow": settings.POSTGRES_MAX_OVERFLOW,
        # Reconnect rather than handing out a socket the database or an
        # intermediate proxy has already closed.
        "pool_pre_ping": True,
    }
)

engine: Engine = create_engine(
    _uri,
    echo=False,
    **_pool_kwargs,  # pyright: ignore[reportArgumentType]
)
