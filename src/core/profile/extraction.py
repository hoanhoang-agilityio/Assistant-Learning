"""LLM structured profile extraction from natural language queries."""

from collections.abc import Callable

from langchain_core.messages import HumanMessage, SystemMessage

from core.llm.factory import get_standard_llm
from core.profile.schema import ExtractedProfile

ProfileExtractor = Callable[[str], ExtractedProfile]

_EXTRACTOR_OVERRIDE: ProfileExtractor | None = None

_EXTRACTION_SYSTEM_PROMPT = """You extract fitness profile fields from a user message.

Return a JSON object with three sections: profile, goal, and constraints.

Rules:
- Return only fields explicitly stated or clearly implied in the user message.
- Use null for any field not mentioned or uncertain.
- Convert all measurements to canonical units before returning:
  - height → height_cm (centimeters)
  - weight → current_weight_kg / target_weight_kg (kilograms)
- Resolve relative weight goals into target_weight_kg when current weight is known
  (e.g. "lose 2 kg" at 75 kg → target_weight_kg: 73).
- Map training frequency to constraints.days_per_week (0 if sedentary, 1–6 otherwise).
- Do not populate activity_level; it is derived from days_per_week downstream.
- Use canonical enum values for goal and equipment.
- Do not invent values."""


def configure_profile_extractor(extractor: ProfileExtractor | None) -> None:
    """Override the profile extractor (used in tests)."""
    global _EXTRACTOR_OVERRIDE
    _EXTRACTOR_OVERRIDE = extractor


def extract_profile_from_query(query: str) -> ExtractedProfile:
    """Extract structured profile fields from a user query via LLM structured output."""
    if _EXTRACTOR_OVERRIDE is not None:
        return _EXTRACTOR_OVERRIDE(query)
    llm = get_standard_llm().with_structured_output(ExtractedProfile)
    return llm.invoke(
        [
            SystemMessage(content=_EXTRACTION_SYSTEM_PROMPT),
            HumanMessage(content=query),
        ]
    )
