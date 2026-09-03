"""The user's stored profile and training plan: loading it, saving it."""

from typing import Any

from pydantic import ValidationError

from src.runtime import MemoryScope
from src.schemas import UserProfile
from src.services.memory import recall, recall_plan, save
from src.services.nutrition import calc_macros

PROFILE_KEY = "profile"

# Derived rather than restated: a field the coach agent cannot run without is exactly a
# field on ``UserProfile`` with no default, and declaration order is the order to ask in.
REQUIRED_PROFILE_FIELDS: tuple[str, ...] = tuple(
    name for name, field in UserProfile.model_fields.items() if field.is_required()
)


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


def nutrition_targets(profile: dict | None) -> dict | None:
    """The calorie and macro targets a profile works out to, or None when it cannot be computed."""

    if not profile:
        return None

    try:
        return calc_macros(UserProfile.model_validate(profile)).model_dump(mode="json")
    except ValidationError:
        return None


async def load_current_plan(user_id: str) -> dict | None:
    """Load the user's current training plan from long-term memory."""

    return await recall_plan(user_id)


async def save_profile(user_id: str, updates: dict[str, Any]) -> dict[str, Any]:
    """Merge new fields into the user's stored profile and persist the result."""

    return await save(user_id, MemoryScope.FACTS, PROFILE_KEY, updates)
