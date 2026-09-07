"""The user's long-term memory: the profile facts and the current plan.

One accessor set over ``BaseStore``. Everything here is keyed by ``user_id`` and outlives
the thread it was written on — the checkpointer holds the run, this holds the user.
"""

from typing import Any

from src.runtime import (
    MemoryScope,
    graph_runtime,
    namespace_for,
    plan_namespace,
)

CURRENT_PLAN_KEY = "current"


async def recall(user_id: str, scope: MemoryScope, key: str) -> dict | None:
    """Read one entry from a user's long-term memory."""

    store = await graph_runtime.store()
    item = await store.aget(namespace_for(user_id, scope), key)

    return dict(item.value) if item is not None else None


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
