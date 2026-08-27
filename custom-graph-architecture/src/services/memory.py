"""The user's long-term memory: preferences, accumulated knowledge and facts.

One accessor set over ``BaseStore`` for all three scopes in ``MemoryScope``. Everything
here is keyed by ``user_id`` and outlives the thread it was written on — the checkpointer
holds the run, this holds the user.
"""

import asyncio
from dataclasses import dataclass
from typing import Any

from src.core.langgraph.runtime import (
    MemoryScope,
    graph_runtime,
    namespace_for,
    plan_namespace,
)

CURRENT_PLAN_KEY = "current"

# A user with more entries than this in one scope has a runaway writer, not a long history.
MAX_ENTRIES_PER_SCOPE = 100


@dataclass(frozen=True, slots=True)
class UserMemory:
    """What the store knows about a user beyond the profile fields the coach requires."""

    preferences: dict[str, Any]
    knowledge: dict[str, Any]

    @property
    def is_empty(self) -> bool:
        """Whether nothing has been recorded for this user in either scope."""
        return not self.preferences and not self.knowledge


async def recall(user_id: str, scope: MemoryScope, key: str) -> dict | None:
    """Read one entry from a user's long-term memory."""

    store = await graph_runtime.store()
    item = await store.aget(namespace_for(user_id, scope), key)

    return dict(item.value) if item is not None else None


async def recall_scope(user_id: str, scope: MemoryScope) -> dict[str, Any]:
    """Read every entry a user has in one scope, keyed as it was written."""

    store = await graph_runtime.store()
    items = await store.asearch(
        namespace_for(user_id, scope), limit=MAX_ENTRIES_PER_SCOPE
    )

    return {item.key: dict(item.value) for item in items}


async def save(
    user_id: str, scope: MemoryScope, key: str, value: dict[str, Any]
) -> dict[str, Any]:
    """Merge new values into one memory entry and persist the result."""

    store = await graph_runtime.store()
    merged = (await recall(user_id, scope, key) or {}) | value
    await store.aput(namespace_for(user_id, scope), key, merged)

    return merged


async def delete(user_id: str, scope: MemoryScope, key: str) -> None:
    """Delete one entry from a user's long-term memory."""

    store = await graph_runtime.store()
    await store.adelete(namespace_for(user_id, scope), key)


async def load_user_memory(user_id: str) -> UserMemory:
    """Load a user's stated preferences and accumulated knowledge together."""

    preferences, knowledge = await asyncio.gather(
        recall_scope(user_id, MemoryScope.PREFERENCES),
        recall_scope(user_id, MemoryScope.KNOWLEDGE),
    )

    return UserMemory(preferences=preferences, knowledge=knowledge)


async def recall_plan(user_id: str) -> dict | None:
    """Read the user's current training plan from long-term memory."""

    store = await graph_runtime.store()
    item = await store.aget(plan_namespace(user_id), CURRENT_PLAN_KEY)

    return dict(item.value) if item is not None else None


async def save_plan(user_id: str, plan: dict[str, Any]) -> dict[str, Any]:
    """Write the user's current training plan to long-term memory."""

    store = await graph_runtime.store()
    await store.aput(plan_namespace(user_id), CURRENT_PLAN_KEY, plan)

    return plan
