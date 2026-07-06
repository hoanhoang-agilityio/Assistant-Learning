"""LLM structured profile extraction from natural language queries."""

from collections.abc import Callable

from langchain_core.messages import HumanMessage, SystemMessage

from core.llm.factory import invoke_standard_structured_output
from core.profile.schema import ExtractedProfile

ProfileExtractor = Callable[[str], ExtractedProfile]

_EXTRACTOR_OVERRIDE: ProfileExtractor | None = None

_EXTRACTION_SYSTEM_PROMPT = """You extract structured fitness profile information from a user's message.

Return ONLY a valid JSON object with exactly three top-level sections:
{
  "profile": {...},
  "goal": {...},
  "constraints": {...}
}

Rules:

1. Extraction
- Extract only information explicitly stated or clearly implied by the user.
- If a field is missing or uncertain, return null.
- Never hallucinate or guess missing values.

2. Canonical units
Convert measurements before returning:
- height -> height_cm (integer, centimeters)
- weight -> current_weight_kg / target_weight_kg (number, kilograms)

3. Allowed derivations
Only the following derivations are allowed:
- Convert measurement units.
- Resolve relative weight goals into target_weight_kg when current_weight_kg is known.
  Example:
    current_weight_kg = 75
    "lose 2 kg"
    -> target_weight_kg = 73

Do NOT derive any other values.

4. Training frequency
Map training frequency into:
constraints.days_per_week

Examples:
- "4-day workout"
- "train 4 times a week"
- "work out four days weekly"
-> days_per_week = 4

Use:
- 0 if the user explicitly says they are sedentary or do not exercise.
- 1–6 when explicitly stated.
- null if not mentioned.

Do NOT populate activity_level.
It will be derived downstream.

5. Canonical enums

goal.goal must be one of:
- fat_loss
- muscle_gain
- recomposition
- maintenance

constraints.equipment must be one of:
- gym
- home
- bodyweight

If equipment is not mentioned, return null.

6. Never infer
Do NOT infer or calculate:
- activity_level
- BMI
- BMR
- TDEE
- calorie targets
- macro targets
- body fat percentage
- fitness experience
- medical conditions
- training intensity
- session duration
- high_protein

unless they are explicitly stated by the user.

Return JSON only.
"""


def configure_profile_extractor(extractor: ProfileExtractor | None) -> None:
    """Override the profile extractor (used in tests)."""
    global _EXTRACTOR_OVERRIDE
    _EXTRACTOR_OVERRIDE = extractor


def extract_profile_from_query(query: str) -> ExtractedProfile:
    """Extract structured profile fields from a user query via LLM structured output."""
    if _EXTRACTOR_OVERRIDE is not None:
        return _EXTRACTOR_OVERRIDE(query)
    return invoke_standard_structured_output(
        ExtractedProfile,
        [
            SystemMessage(content=_EXTRACTION_SYSTEM_PROMPT),
            HumanMessage(content=query),
        ],
    )
