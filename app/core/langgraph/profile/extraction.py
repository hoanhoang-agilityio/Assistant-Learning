"""Turning what the user said into profile fields the rest of the system trusts.

Pure functions, no I/O and no model call. The call itself lives in the
supervisor's ``extract_profile`` middleware; what is here is the part that must
be identical wherever it runs — which vocabularies are recognised, and what
counts as a goal conflict worth interrupting the user for.

``profile/`` sits outside the agent registry. What earns a place there is an
independent workflow with its own state and contract; this is orchestration the
supervisor owns, and after the conversion it is middleware rather than a root
node (``docs/supervisor-architecture.md`` §12).
"""

from app.core.logging import logger
from app.schemas.graph import GoalConflict, ProfileExtraction
from app.services.rubrics import contraindications

# The vocabularies downstream code matches on. An extraction outside these sets
# is silently dropped rather than stored, because `calc_macros` raises on an
# unknown activity level and the candidate filter would silently match nothing
# for an unknown equipment token.
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

# How much of a free-text injury description is kept. Long enough to be a real
# description, short enough that a paragraph cannot be smuggled into a prompt.
_MAX_UNMAPPED_INJURY = 200


def clean_extraction(extraction: ProfileExtraction) -> dict:
    """Drop nulls and values outside the controlled vocabularies.

    A token the rest of the system does not recognise is worse than a missing
    one: an unknown ``activity_level`` makes ``calc_macros`` raise, and an
    unknown equipment string silently matches no exercise. Discarding it means
    the profile precondition asks again, which is the correct recovery.

    ``implied_goal`` is removed here rather than filtered downstream. What this
    returns is merged straight into the profile, so leaving it in would store the
    very guess the field exists to avoid storing.

    Args:
        extraction: The model's structured output.

    Returns:
        Only the profile fields that are present and valid.
    """
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
            # An empty list is a real answer ("no injuries") and must survive.
            clean[key] = [item for item in value if item in contraindications()["injuries"]]
        else:
            clean[key] = value

    return clean


def goal_conflict(extraction: ProfileExtraction, merged: dict) -> GoalConflict | None:
    """Decide whether this turn's implied goal contradicts the stored one.

    Deliberately narrow. A conflict needs an implied goal in the vocabulary, a
    stored goal to contradict, and the two to actually differ — anything less is
    not a question worth interrupting the user with.

    Nothing is raised when the user *stated* a goal this turn: ``goal`` has
    already overwritten the stored one by the time this runs, so ``merged`` holds
    what they just said and there is nothing to ask about.

    Args:
        extraction: The model's structured output, before cleaning.
        merged: The profile after this turn's stated facts were applied.

    Returns:
        The conflict, or ``None`` when there is nothing to ask.
    """
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
    """Say out loud that a declared injury has no screening rule.

    Silence here reads as "checked and fine", which is the opposite of the
    truth — nothing in the pipeline accounts for it.

    Args:
        profile: The merged profile.

    Returns:
        The sentence to include in a plan answer, or an empty string.
    """
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
    """Log a discarded extraction so a bad prompt is visible in the trace.

    Args:
        key: The profile field being discarded.
        value: The value that failed its vocabulary check.
    """
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
