"""User profile persistence and the required-field gate.

``REQUIRED_FIELDS`` is the load-bearing part. It is a **constant**, not a
model's judgment about whether it has enough information given the choice, a model eventually decides a profile looks complete and
the pipeline proceeds with ``activity_level = None``, producing a TDEE that is
wrong by several hundred calories and looks authoritative.
"""

import hashlib
import json
from datetime import UTC, datetime
from typing import Any

from sqlmodel import Session, select

from app.core.logging import logger
from app.models.database import engine
from app.models.profile import UserProfile
from app.schemas.graph import Intent

# Fields each intent cannot proceed without. `build_plan` is the full set from
# Without any one of these, either the template query or the macro
# calculation has no answer.
REQUIRED_FIELDS: dict[Intent, tuple[str, ...]] = {
    "build_plan": (
        "weight_kg",
        "height_cm",
        "age",
        "sex",
        "activity_level",
        "days_per_week",
        "equipment",
        "injuries",
        "goal",
        # Required because `filter_candidates` filters on it. Left unasked it
        # defaulted to 1, which is not a neutral default: it is the strictest
        # possible filter, and it drops whole movement patterns off the plan
        # without the user ever having claimed to be a beginner.
        "level",
    ),
    # A change re-runs calc_macro and all three verifiers, so it needs the same
    # inputs as a build.
    "change_plan": (
        "weight_kg",
        "height_cm",
        "age",
        "sex",
        "activity_level",
        "days_per_week",
        "equipment",
        "injuries",
        "goal",
        "level",
    ),
    # Scoring a pasted plan needs the body data the macro and injury checks read,
    # but not the programme-shaping fields.
    "check": ("weight_kg", "height_cm", "age", "sex", "activity_level", "injuries"),
    "revert": (),
    "general_qa": (),
}

# Human-readable labels for `ask_missing`, so the question does not name
# database columns at the user.
FIELD_LABELS: dict[str, str] = {
    "weight_kg": "your body weight (kg)",
    "height_cm": "your height (cm)",
    "age": "your age",
    "sex": "your sex (male or female — it changes the calorie equation)",
    "activity_level": "how active your day-to-day life is outside training "
    "(sedentary, light, moderate, active, very active)",
    "days_per_week": "how many days a week you can train",
    "equipment": "what equipment you have access to",
    "injuries": "any injuries or joints that give you trouble (or 'none')",
    "goal": "your goal (fat loss, muscle gain, recomp or general health)",
    "level": "your training experience (1 = new, 5 = advanced)",
}

# Fields the user answers as "none" rather than leaving blank. An empty list is
# a complete answer for these; for every other field, empty means unanswered.
_EMPTY_IS_AN_ANSWER = frozenset({"injuries"})

_PERSISTED_FIELDS = (
    "weight_kg",
    "height_cm",
    "age",
    "sex",
    "activity_level",
    "days_per_week",
    "level",
    "goal",
    "equipment",
    "injuries",
    "preferences",
    "unmapped_injury",
)


async def get_profile(user_id: int) -> dict[str, Any]:
    """Load a user's profile as a plain dict.

    Args:
        user_id: Owner of the profile.

    Returns:
        The profile, or an empty dict when the user has none yet. Never
        ``None`` — every caller treats a missing profile as an empty one and
        lets ``check_required`` decide what to ask for.
    """
    with Session(engine) as session:
        row = session.exec(select(UserProfile).where(UserProfile.user_id == user_id)).first()

    if row is None:
        return {}
    # `level` is returned exactly as stored, including `None`. Coalescing an
    # unanswered level to 1 here made it indistinguishable from a user who said
    # "beginner", so `missing_fields` never asked — and `filter_candidates`
    # then excluded every skill-2 exercise, silently dropping any pattern whose
    # cheapest option is skill 2. The defensive floor belongs at the point of
    # use, in `filter_candidates`, not on the way out of the database.
    return {field: getattr(row, field) for field in _PERSISTED_FIELDS}


async def upsert_profile(user_id: int, profile: dict[str, Any]) -> None:
    """Write a profile back, creating the row on first use.

    Only keys present in ``profile`` are written, so a partial extraction cannot
    blank out a field the user answered three turns ago.

    Args:
        user_id: Owner of the profile.
        profile: Fields to persist.
    """
    with Session(engine) as session:
        row = session.exec(select(UserProfile).where(UserProfile.user_id == user_id)).first()
        if row is None:
            row = UserProfile(user_id=user_id)

        for field in _PERSISTED_FIELDS:
            if field in profile and profile[field] is not None:
                setattr(row, field, profile[field])

        row.updated_at = datetime.now(UTC)
        session.add(row)
        session.commit()

    logger.info(
        "profile_saved", user_id=user_id, fields=sorted(set(profile) & set(_PERSISTED_FIELDS))
    )


def missing_fields(profile: dict[str, Any], intent: Intent) -> list[str]:
    """Return the required fields this intent still lacks.

    Args:
        profile: The profile as extracted so far.
        intent: The classified intent.

    Returns:
        Missing field names, in the order ``REQUIRED_FIELDS`` declares them so
        the question reads consistently. Empty when the profile is sufficient.
    """
    required = REQUIRED_FIELDS.get(intent, ())
    return [field for field in required if not _is_answered(profile, field)]


def _is_answered(profile: dict[str, Any], field: str) -> bool:
    """Decide whether a field has a usable value.

    ``injuries`` is the special case: an empty list means "I have none", which
    is a complete answer. For every other field an empty value means the user
    has not said, and asking again is correct.

    Args:
        profile: The profile.
        field: Field name.

    Returns:
        ``True`` when the field is answered.
    """
    # An injury we could not map still counts as answered. The user told us;
    # asking again produces the same unmappable description and traps them in a
    # loop they cannot escape, which is how a required field with a two-value
    # vocabulary locks out everyone else.
    if field == "injuries" and profile.get("unmapped_injury"):
        return True

    if field not in profile:
        return False
    value = profile[field]
    if value is None:
        return False
    if field in _EMPTY_IS_AN_ANSWER:
        return isinstance(value, list)
    return value != "" and value != []


def profile_hash(profile: dict[str, Any]) -> str:
    """Fingerprint the profile fields that can change a verify result.

    Used by the revert gate, if the hash is unchanged since a plan was
    stored, re-running the verifiers is guaranteed to produce the same verdict
    and can be skipped. If it moved — the user lost 3 kg, or declared a new
    injury — the stored verdict no longer describes them and the plan must be
    re-checked.

    Excludes ``preferences``, which steers exercise choice but cannot change
    whether a plan passes.

    Args:
        profile: The profile to fingerprint.

    Returns:
        A 16-character hex digest.
    """
    material = {field: profile.get(field) for field in _PERSISTED_FIELDS if field != "preferences"}
    encoded = json.dumps(material, sort_keys=True, default=str).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()[:16]


__all__ = [
    "FIELD_LABELS",
    "REQUIRED_FIELDS",
    "get_profile",
    "missing_fields",
    "profile_hash",
    "upsert_profile",
]
