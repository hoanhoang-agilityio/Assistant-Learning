from collections.abc import Iterator
from contextlib import contextmanager

from langgraph.checkpoint.postgres import PostgresSaver

from core.config.settings import Settings, get_settings


@contextmanager
def postgres_checkpointer(settings: Settings | None = None) -> Iterator[PostgresSaver]:
    """Yield a configured Postgres checkpointer for LangGraph."""
    resolved_settings = settings or get_settings()
    with PostgresSaver.from_conn_string(resolved_settings.checkpointer_dsn) as checkpointer:
        checkpointer.setup()
        yield checkpointer
