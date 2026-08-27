"""The user's stored profile and training plan: loading it, merging it, saving it."""

import asyncio
from dataclasses import dataclass
from typing import Any

from src.core.langgraph.runtime import MemoryScope
from src.schemas import UserProfile
from src.schemas.domain.profile import (
    MAX_AGE,
    MAX_TRAINING_DAYS,
    MIN_AGE,
    MIN_TRAINING_DAYS,
)
from src.services.memory import recall, recall_plan, save
from src.services.turn import EXTRACTABLE_FIELDS, InjuryStatement, ProfileStatement

PROFILE_KEY = "profile"

# Derived rather than restated: a field the coach agent cannot run without is exactly a
# field on ``UserProfile`` with no default, and declaration order is the order to ask in.
REQUIRED_PROFILE_FIELDS: tuple[str, ...] = tuple(
    name for name, field in UserProfile.model_fields.items() if field.is_required()
)

PROFILE_BOUNDS: dict[str, tuple[float, float]] = {
    "age": (MIN_AGE, MAX_AGE),
    "training_days_per_week": (MIN_TRAINING_DAYS, MAX_TRAINING_DAYS),
}
POSITIVE_PROFILE_FIELDS: tuple[str, ...] = (
    "height_cm",
    "current_weight_kg",
    "target_weight_kg",
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


def _is_in_range(name: str, value: Any) -> bool:
    """Report whether a stated value is plausible enough to store."""

    if name in PROFILE_BOUNDS:
        low, high = PROFILE_BOUNDS[name]
        return low <= value <= high
    if name in POSITIVE_PROFILE_FIELDS:
        return value > 0
    return True


def usable_profile_fields(statement: ProfileStatement) -> dict[str, Any]:
    """Keep the stated scalar fields that carry a value and are within range."""

    # JSON mode so enum members reach the store as the plain strings they read back as.
    dumped = statement.model_dump(mode="json")
    usable: dict[str, Any] = {}
    for name in EXTRACTABLE_FIELDS:
        value = dumped[name]
        if value is None:
            continue
        if not _is_in_range(name, value):
            continue
        usable[name] = value
    return usable


def _body_part_key(body_part: object) -> str:
    """The identity an injury is matched on across turns."""

    return str(body_part).strip().lower()


def merge_injuries(
    stored: list[dict] | None, stated: list[InjuryStatement]
) -> list[dict]:
    """Upsert each reported injury onto the stored list, matched by body part."""

    merged = [dict(injury) for injury in stored or []]
    positions = {
        _body_part_key(injury.get("body_part")): position
        for position, injury in enumerate(merged)
    }

    for statement in stated:
        update = {
            name: value
            for name, value in statement.model_dump(mode="json").items()
            if value is not None
        }
        position = positions.get(_body_part_key(statement.body_part))
        if position is None:
            positions[_body_part_key(statement.body_part)] = len(merged)
            merged.append(update)
        else:
            merged[position] = merged[position] | update

    return merged


def merge_profile_updates(
    profile: dict | None, statement: ProfileStatement
) -> dict[str, Any]:
    """Fold one turn's stated values, injuries and revision flags into a runtime profile."""

    merged = dict(profile or {})
    updates = usable_profile_fields(statement)
    merged.update(updates)

    if statement.injuries:
        merged["injuries"] = merge_injuries(merged.get("injuries"), statement.injuries)

    for name in statement.fields_to_revise:
        if name not in updates:
            merged[name] = None

    return merged


def pending_revision_fields(
    profile: dict | None, revision_fields: list[str]
) -> list[str]:
    """Revision-flagged fields, in the order given, that are still blank in ``profile``."""

    return [name for name in revision_fields if _is_blank((profile or {}).get(name))]


async def save_profile(user_id: str, updates: dict[str, Any]) -> dict[str, Any]:
    """Merge new fields into the user's stored profile and persist the result."""

    return await save(user_id, MemoryScope.FACTS, PROFILE_KEY, updates)
