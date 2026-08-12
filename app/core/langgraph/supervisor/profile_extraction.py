"""Clean and reconcile profile facts extracted for the supervisor."""

from app.core.logging import logger
from app.schemas.graph import GoalConflict, ProfileExtraction
from app.services.rubrics import contraindications

SEXES = ("male", "female")
ACTIVITY_LEVELS = ("sedentary", "light", "moderate", "active", "very_active")
GOALS = ("fat_loss", "muscle_gain", "recomp", "general_health")
EQUIPMENT_TOKENS = frozenset(
    {
        "barbell",
        "dumbbell",
        "cable",
        "machine",
        "smith_machine",
        "kettlebell",
        "resistance_band",
        "bodyweight",
        "pull_up_bar",
        "dip_station",
    }
)
_MIN_LEVEL, _MAX_LEVEL = 1, 5
_MAX_UNMAPPED_INJURY = 200


def clean_extraction(extraction: ProfileExtraction) -> dict:
    """Drop nulls and values outside the controlled vocabularies."""
    raw = extraction.model_dump(exclude_none=True)
    raw.pop("implied_goal", None)
    clean: dict = {}
    for key, value in raw.items():
        if key == "sex" and value not in SEXES:
            _drop(key, value)
        elif key == "activity_level" and value not in ACTIVITY_LEVELS:
            _drop(key, value)
        elif key == "goal" and value not in GOALS:
            _drop(key, value)
        elif key == "level" and not _MIN_LEVEL <= value <= _MAX_LEVEL:
            _drop(key, value)
        elif key == "equipment":
            kept = [item for item in value if item in EQUIPMENT_TOKENS]
            if kept:
                clean[key] = sorted(set(kept))
        elif key == "unmapped_injury":
            clean[key] = str(value)[:_MAX_UNMAPPED_INJURY]
        elif key == "injuries":
            clean[key] = [item for item in value if item in contraindications()["injuries"]]
        else:
            clean[key] = value
    return clean


def goal_conflict(extraction: ProfileExtraction, merged: dict) -> GoalConflict | None:
    """Decide whether this turn's implied goal contradicts the stored one."""
    implied = extraction.implied_goal
    if implied not in GOALS:
        if implied is not None:
            _drop("implied_goal", implied)
        return None
    stored = merged.get("goal")
    if not stored or stored == implied:
        return None
    return GoalConflict(stored=stored, implied=implied)


def unmapped_injury_note(profile: dict) -> str:
    """Say out loud that a declared injury has no screening rule."""
    injury = profile.get("unmapped_injury")
    if not injury:
        return ""
    return (
        f'The user mentioned: "{injury}". There is no screening rule for that, so '
        "nothing in this plan accounts for it. Say so once: the exercise selection is "
        "unreviewed for that problem, and a professional should see it if it is sharp, "
        "new or getting worse."
    )


def _drop(key: str, value: object) -> None:
    """Log a discarded extraction so a bad prompt is visible in the trace."""
    logger.warning("profile_value_outside_vocabulary", field=key, value=str(value))


__all__ = [
    "ACTIVITY_LEVELS",
    "EQUIPMENT_TOKENS",
    "GOALS",
    "SEXES",
    "clean_extraction",
    "goal_conflict",
    "unmapped_injury_note",
]
