"""The user's stored profile and training plan: loading it, extracting it, saving it."""

import asyncio
from dataclasses import dataclass
from functools import lru_cache
from typing import Any, Literal

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

PROFILE_BOUNDS: dict[str, tuple[float, float]] = {
    "age": (13, 100),
    "training_days_per_week": (1, 7),
}
POSITIVE_PROFILE_FIELDS: tuple[str, ...] = (
    "height_cm",
    "current_weight_kg",
    "target_weight_kg",
)

_EXTRACTOR_TOKEN_LIMIT = 256


class ProfileExtraction(BaseModel):
    """Structured output for the profile extractor."""

    age: int | None = Field(default=None, description="Age in years.")
    sex: Literal["MALE", "FEMALE"] | None = Field(default=None)
    height_cm: float | None = Field(
        default=None, description="Height in centimetres.")
    current_weight_kg: float | None = Field(
        default=None, description="Weight in kg.")
    target_weight_kg: float | None = Field(
        default=None, description="Goal weight in kg."
    )
    activity_level: (
        Literal["SEDENTARY", "LIGHT", "MODERATE",
                "VERY_ACTIVE", "EXTRA_ACTIVE"] | None
    ) = Field(default=None)
    goal: (
        Literal["FAT_LOSS", "MUSCLE_GAIN",
                "MAINTENANCE", "STRENGTH", "GENERAL_FITNESS"]
        | None
    ) = Field(default=None)
    training_days_per_week: int | None = Field(default=None)


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
        max_completion_tokens=_EXTRACTOR_TOKEN_LIMIT,
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
    """Keep the extracted fields that were stated and are within range."""

    usable: dict[str, Any] = {}
    for name, value in extraction.model_dump().items():
        if value is None:
            continue
        if not _is_in_range(name, value):
            continue
        usable[name] = value
    return usable


async def extract_profile_fields(user_reply: str) -> dict[str, Any]:
    """Read the profile facts the user stated in one reply."""

    if not user_reply.strip():
        return {}

    try:
        extractor = _build_extractor().with_structured_output(ProfileExtraction)
        extraction = await extractor.ainvoke(
            build_profile_extractor_messages(user_reply)
        )
    except Exception as error:
        # The collection loop asks again, and its retry counter bounds that — so a failed
        # extraction costs one more question rather than the whole run.
        logger.exception("profile_extraction_failed", error=str(error))
        return {}

    return usable_profile_fields(extraction)


async def save_profile(user_id: str, updates: dict[str, Any]) -> dict[str, Any]:
    """Merge new fields into the user's stored profile and persist the result."""

    store = await graph_runtime.store()
    namespace = namespace_for(user_id, MemoryScope.FACTS)
    stored = await load_profile(user_id) or {}
    merged = stored | updates

    await store.aput(namespace, PROFILE_KEY, merged)

    return merged
