"""The persistence seam for the graph.

The graph needs two things from storage and does not care what backs them:

- a **checkpointer** — short-term memory. It persists ``GraphState`` after every node, which
  is what makes the spec's two ``interrupt()`` gates work: ``wait_for_user`` and
  ``hitl_review`` suspend the graph and the state survives until the next request.
- a **store** — long-term memory. User preferences, accumulated behavioural knowledge and
  facts, keyed by user rather than by thread, outliving any one conversation.

Both are returned as LangGraph's own ABCs, ``BaseCheckpointSaver`` and ``BaseStore``, rather
than as concrete Postgres classes. That is what keeps the storage choice swappable: a Redis,
SQLite or Mongo backend is a new ``GraphRuntime`` subclass plus one line in the registry, and
no node, agent or façade changes — they only ever see the ABCs.
"""

from abc import ABC, abstractmethod

from langgraph.checkpoint.base import BaseCheckpointSaver
from langgraph.store.base import BaseStore


class GraphRuntime(ABC):
    """Supplies the graph's persistence backends and owns their lifecycle.

    Implementations are expected to initialise lazily and cache: schema setup is idempotent
    but not free, so it belongs on first use rather than on every request.
    """

    @abstractmethod
    async def checkpointer(self) -> BaseCheckpointSaver:
        """Return the process-wide checkpointer, initialising it on first call.

        Returns:
            BaseCheckpointSaver: Short-term memory for the graph, keyed by ``thread_id``.
        """

    @abstractmethod
    async def store(self) -> BaseStore:
        """Return the process-wide long-term store, initialising it on first call.

        Returns:
            BaseStore: Long-term memory, addressed by namespace — see ``namespaces``.
        """

    @abstractmethod
    async def close(self) -> None:
        """Release any resources held by the backend. Safe to call when never opened."""
