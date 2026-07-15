"""LLM structured profile extraction from natural language queries."""

from collections.abc import Callable

from langchain_core.messages import HumanMessage, SystemMessage

from core.llm.factory import invoke_standard_structured_output
from core.llm.metrics import reset_llm_metrics_node, set_llm_metrics_node
from core.llm.prompt_fragments import JSON_ONLY_INSTRUCTION
from core.profile.schema import ExtractedProfile

ProfileExtractor = Callable[[str], ExtractedProfile]

_EXTRACTOR_OVERRIDE: ProfileExtractor | None = None

_EXTRACTION_SYSTEM_PROMPT = (
    """You extract structured fitness profile information from a user's message
into the given schema. Follow the `description` on each field for what to extract
and how to derive it.

General policy:
- Extract only information explicitly stated or clearly implied. Never hallucinate or guess.
- Leave a field null if not mentioned or not derivable from stated facts.
- All three sections (profile, goal, constraints) must be objects, never null themselves.

Do NOT populate or infer the following — they are computed downstream from other data,
not extracted from text: activity_level, BMI, BMR, TDEE, calorie targets, macro targets,
body fat percentage, fitness experience, medical conditions, training intensity.
"""
    + JSON_ONLY_INSTRUCTION
    + "\n"
)


def configure_profile_extractor(extractor: ProfileExtractor | None) -> None:
    """Override the profile extractor (used in tests)."""
    global _EXTRACTOR_OVERRIDE
    _EXTRACTOR_OVERRIDE = extractor


def extract_profile_from_query(query: str) -> ExtractedProfile:
    """Extract structured profile fields from a user query via LLM structured output."""
    if _EXTRACTOR_OVERRIDE is not None:
        return _EXTRACTOR_OVERRIDE(query)
    token = set_llm_metrics_node("profile_extraction")
    try:
        return invoke_standard_structured_output(
            ExtractedProfile,
            [
                SystemMessage(content=_EXTRACTION_SYSTEM_PROMPT),
                HumanMessage(content=query),
            ],
            prompt_cache_key="profile_extraction",
        )
    finally:
        reset_llm_metrics_node(token)
