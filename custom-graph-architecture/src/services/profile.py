"""The user's stored profile and training plan: loading it, saving it."""

import asyncio
from dataclasses import dataclass
from typing import Any

from src.runtime import MemoryScope
from src.schemas import UserProfile
from src.services.memory import recall, recall_plan, save

PROFILE_KEY = "profile"

# Derived rather than restated: a field the coach agent cannot run without is exactly a
# field on ``UserProfile`` with no default, and declaration order is the order to ask in.
REQUIRED_PROFILE_FIELDS: tuple[str, ...] = tuple(
    name for name, field in UserProfile.model_fields.items() if field.is_required()
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

    return await recall(user_id, MemoryScope.FACTS, PROFILE_KEY)


async def load_current_plan(user_id: str) -> dict | None:
    """Load the user's current training plan from long-term memory."""

    return await recall_plan(user_id)


async def load_user_context(user_id: str) -> UserContext:
    """Load the user's profile and current plan together."""

    profile, plan = await asyncio.gather(
        load_profile(user_id), load_current_plan(user_id)
    )

    return UserContext(profile=profile, plan=plan)


async def save_profile(user_id: str, updates: dict[str, Any]) -> dict[str, Any]:
    """Merge new fields into the user's stored profile and persist the result."""

    return await save(user_id, MemoryScope.FACTS, PROFILE_KEY, updates)
