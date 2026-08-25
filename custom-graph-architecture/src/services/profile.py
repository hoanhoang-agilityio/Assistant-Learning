"""The user's stored profile and training plan: loading it, extracting it, saving it."""

import asyncio
from dataclasses import dataclass
from functools import lru_cache
from typing import Any, Literal, get_args

from langchain_openai import ChatOpenAI
from pydantic import BaseModel, Field

from src.core.configs.config import settings
from src.core.langgraph.prompts import build_profile_extractor_messages
from src.core.langgraph.runtime import (
    MemoryScope,
    graph_runtime,
    namespace_for,
    plan_namespace,
)
from src.schemas import ActivityLevel, FitnessGoal, Sex, UserProfile
from src.schemas.domain.profile import (
    MAX_AGE,
    MAX_TRAINING_DAYS,
    MIN_AGE,
    MIN_TRAINING_DAYS,
)
from src.utils.logging import logger

PROFILE_KEY = "profile"
CURRENT_PLAN_KEY = "current"

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

_EXTRACTOR_TOKEN_LIMIT = 256

FieldName = Literal[
    "age",
    "sex",
    "height_cm",
    "current_weight_kg",
    "target_weight_kg",
    "activity_level",
    "goal",
    "training_days_per_week",
]
EXTRACTABLE_FIELDS: tuple[str, ...] = get_args(FieldName)


class ProfileExtraction(BaseModel):
    """Structured output for the profile extractor."""

    age: int | None = Field(default=None, description="Age in years.")
    sex: Sex | None = Field(default=None)
    height_cm: float | None = Field(
        default=None, description="Height in centimetres.")
    current_weight_kg: float | None = Field(
        default=None, description="Weight in kg.")
    target_weight_kg: float | None = Field(
        default=None, description="Goal weight in kg."
    )
    activity_level: ActivityLevel | None = Field(default=None)
    goal: FitnessGoal | None = Field(default=None)
    training_days_per_week: int | None = Field(default=None)
    fields_to_revise: list[FieldName] = Field(
        default_factory=list,
        description="Fields the user wants changed but did not restate a value for.",
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


@lru_cache
def _build_extractor() -> ChatOpenAI:
    """Build the shared extraction model from application settings."""
    return ChatOpenAI(
        api_key=settings.OPENAI_API_KEY,
        model=settings.DEFAULT_LLM_MODEL,
    )


def _is_in_range(name: str, value: Any) -> bool:
    """Report whether an extracted value is plausible enough to store."""

    if name in PROFILE_BOUNDS:
        low, high = PROFILE_BOUNDS[name]
        return low <= value <= high
    if name in POSITIVE_PROFILE_FIELDS:
        return value > 0
    return True


def usable_profile_fields(extraction: ProfileExtraction) -> dict[str, Any]:
    """Keep the extracted scalar fields that were stated and are within range."""

    # JSON mode so enum members reach the store as the plain strings they read back as.
    dumped = extraction.model_dump(mode="json")
    usable: dict[str, Any] = {}
    for name in EXTRACTABLE_FIELDS:
        value = dumped[name]
        if value is None:
            continue
        if not _is_in_range(name, value):
            continue
        usable[name] = value
    return usable


async def extract_profile_fields(
    user_reply: str, fields_in_focus: list[str] | None = None
) -> ProfileExtraction:
    """Read the profile facts and revision requests the user stated in one reply."""

    if not user_reply.strip():
        return ProfileExtraction()

    try:
        extractor = _build_extractor().with_structured_output(ProfileExtraction)
        extraction = await extractor.ainvoke(
            build_profile_extractor_messages(user_reply, fields_in_focus)
        )
    except Exception as error:
        # The collection loop asks again, and its retry counter bounds that — so a failed
        # extraction costs one more question rather than the whole run.
        logger.exception("profile_extraction_failed", error=str(error))
        return ProfileExtraction()

    return extraction


def merge_profile_updates(profile: dict | None, extraction: ProfileExtraction) -> dict[str, Any]:
    """Fold one reply's stated values and revision flags into a runtime profile."""

    merged = dict(profile or {})
    updates = usable_profile_fields(extraction)
    merged.update(updates)

    for name in extraction.fields_to_revise:
        if name not in updates:
            merged[name] = None

    return merged


def pending_revision_fields(profile: dict | None, revision_fields: list[str]) -> list[str]:
    """Revision-flagged fields, in the order given, that are still blank in ``profile``."""

    return [name for name in revision_fields if _is_blank((profile or {}).get(name))]


async def save_profile(user_id: str, updates: dict[str, Any]) -> dict[str, Any]:
    """Merge new fields into the user's stored profile and persist the result."""

    store = await graph_runtime.store()
    namespace = namespace_for(user_id, MemoryScope.FACTS)
    stored = await load_profile(user_id) or {}
    merged = stored | updates

    await store.aput(namespace, PROFILE_KEY, merged)

    return merged


_pending_saves: set[asyncio.Task] = set()


def save_profile_in_background(user_id: str, profile: dict[str, Any]) -> asyncio.Task:
    """Persist the profile without blocking the caller."""

    task = asyncio.create_task(save_profile(user_id, profile))
    _pending_saves.add(task)
    task.add_done_callback(_forget_and_log)
    return task


def _forget_and_log(task: asyncio.Task) -> None:
    """Drop a finished background save from the registry, logging any failure."""

    _pending_saves.discard(task)
    if task.cancelled():
        return
    error = task.exception()
    if error is not None:
        logger.exception("background_profile_save_failed", error=str(error))


async def flush_pending_saves() -> None:
    """Wait for every in-flight background save — call before asserting persisted state."""

    pending = list(_pending_saves)
    if pending:
        await asyncio.gather(*pending, return_exceptions=True)
