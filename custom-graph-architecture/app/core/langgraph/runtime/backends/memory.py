"""In-process implementation of ``GraphRuntime``.

For tests and for running the graph without a database. State lives only in the process, so
a restart loses every suspended ``interrupt()`` — which is exactly why this is not a
production backend, and why ``Settings`` defaults to Postgres.
"""

from langgraph.checkpoint.memory import InMemorySaver
from langgraph.store.memory import InMemoryStore

from app.core.langgraph.runtime.base import GraphRuntime


class InMemoryRuntime(GraphRuntime):
    """Keeps checkpoints and long-term memory in process memory."""

    def __init__(self) -> None:
        self._checkpointer = InMemorySaver()
        self._store = InMemoryStore()

    async def checkpointer(self) -> InMemorySaver:
        """Return the in-process checkpointer.

        Returns:
            InMemorySaver: Short-term memory, discarded when the process exits.
        """
        return self._checkpointer

    async def store(self) -> InMemoryStore:
        """Return the in-process long-term store.

        Returns:
            InMemoryStore: Long-term memory, discarded when the process exits.
        """
        return self._store

    async def close(self) -> None:
        """Drop the retained state. Nothing external is held open."""
        self._checkpointer = InMemorySaver()
        self._store = InMemoryStore()
