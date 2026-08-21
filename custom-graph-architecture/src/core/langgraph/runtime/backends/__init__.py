"""Persistence backend registry: setting value → ``GraphRuntime`` implementation.

The only module that enumerates backends. Adding one — Redis, SQLite, Mongo — is a new
class here plus one entry in ``RUNTIMES`` and one value on ``PersistenceBackend``; nothing
that consumes the runtime changes, because callers only ever see the ABCs in ``base``.
"""

from collections.abc import Callable

from src.core.configs.config import PersistenceBackend
from src.core.langgraph.runtime.backends.memory import InMemoryRuntime
from src.core.langgraph.runtime.backends.postgres import PostgresRuntime
from src.core.langgraph.runtime.base import GraphRuntime

RUNTIMES: dict[PersistenceBackend, Callable[[], GraphRuntime]] = {
    PersistenceBackend.POSTGRES: PostgresRuntime,
    PersistenceBackend.MEMORY: InMemoryRuntime,
}


def build_runtime(backend: PersistenceBackend) -> GraphRuntime:
    """Instantiate the runtime for a backend.

    Args:
        backend: Which persistence backend to construct.

    Returns:
        GraphRuntime: An uninitialised runtime; its backends open on first use.

    Raises:
        ValueError: If the backend has no registered implementation.
    """
    if backend not in RUNTIMES:
        raise ValueError(f"no runtime registered for persistence backend {backend!r}")
    return RUNTIMES[backend]()
