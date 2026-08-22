"""Reads of the user's stored profile and training plan."""

import asyncio
from dataclasses import dataclass

from src.core.langgraph.runtime import (
    MemoryScope,
    graph_runtime,
    namespace_for,
    plan_namespace,
)
from src.utils.logging import logger

PROFILE_KEY = "profile"
CURRENT_PLAN_KEY = "current"

REQUIRED_PROFILE_FIELDS: tuple[str, ...] = (
    "age",
    "sex",
    "height_cm",
    "current_weight_kg",
    "activity_level",
    "goal",
    "training_days_per_week",
)


@dataclass(frozen=True, slots=True)
class UserContext:
    """Everything the coaching branch knows about the user before it starts planning."""

    profile: dict | None = None
    plan: dict | None = None

    @property
    def missing_fields(self) -> list[str]:
        """Required profile fields that are absent or blank, in the order to ask for them."""
        return missing_profile_fields(self.profile)

    @property
    def is_complete(self) -> bool:
        """Whether the profile carries every field the coach agent needs."""
        return not self.missing_fields


def _is_blank(value: object) -> bool:
    """Report whether a stored field carries no usable value."""
    if value is None:
        return True
    return isinstance(value, str) and not value.strip()


def missing_profile_fields(profile: dict | None) -> list[str]:
    """List the required profile fields the coach agent still needs."""

    if not profile:
        return list(REQUIRED_PROFILE_FIELDS)
    return [name for name in REQUIRED_PROFILE_FIELDS if _is_blank(profile.get(name))]


async def load_profile(user_id: str) -> dict | None:
    """Load the user's stored profile from long-term memory."""

    store = await graph_runtime.store()
    item = await store.aget(namespace_for(user_id, MemoryScope.FACTS), PROFILE_KEY)

    return dict(item.value) if item is not None else None


async def load_current_plan(user_id: str) -> dict | None:
    """Load the user's current training plan from long-term memory."""

    store = await graph_runtime.store()
    item = await store.aget(plan_namespace(user_id), CURRENT_PLAN_KEY)
    return dict(item.value) if item is not None else None


async def load_user_context(user_id: str) -> UserContext:
    """Load the user's profile and current plan together."""

    profile, plan = await asyncio.gather(
        load_profile(user_id), load_current_plan(user_id)
    )

    return UserContext(profile=profile, plan=plan)
