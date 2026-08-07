"""Exercise catalog access and the candidate filter.

The filter in ``filter_candidates`` is the load-bearing part of this module.
Every constraint that must not be negotiable — available equipment, skill level,
injury contraindications — is applied here, in code, over catalog metadata. It is
not stated in a prompt, because a prompt-level filter is advisory: a model can
decide the user "probably" owns a barbell, or that one contraindicated exercise
is fine. A set intersection cannot.

``get_exercise_candidates``, the one tool the LLM may call for this data, is a
thin wrapper over ``filter_candidates`` — so there is no path to an unfiltered
list even from inside the model's tool call.

The whole catalog is around 200 rows, so it is cached in process rather than
re-queried per slot. It changes through a seed or a migration, not at runtime.
"""

from sqlmodel import Session, select

from app.core.logging import logger
from app.models.database import engine
from app.models.exercise import Exercise

# Filtering happens over an in-process copy: 200 rows of small arrays is well
# under a megabyte, a build touches every slot, and a per-slot round trip would
# dominate the node's latency. The GIN indexes still matter for the ad-hoc
# queries in `find_alternative` and future admin tooling.
_CACHE: dict[str, dict] | None = None


def _to_dict(exercise: Exercise) -> dict:
    """Convert a catalog row to the plain dict the checks and tools consume.

    Args:
        exercise: The ORM row.

    Returns:
        The exercise as a dict, keyed exactly as the verification checks expect.
    """
    return {
        "exercise_id": exercise.id,
        "name": exercise.name,
        "movement_pattern": exercise.movement_pattern,
        "primary_muscles": list(exercise.primary_muscles),
        "secondary_muscles": list(exercise.secondary_muscles),
        "equipment": list(exercise.equipment),
        "joint_actions": list(exercise.joint_actions),
        "loaded_positions": list(exercise.loaded_positions),
        "contribution": dict(exercise.contribution),
        "skill_level": exercise.skill_level,
        "fatigue_cost": exercise.fatigue_cost,
    }


def load_catalog(refresh: bool = False) -> dict[str, dict]:
    """Return the whole catalog keyed by ``exercise_id``.

    Args:
        refresh: Re-read from Postgres instead of using the cached copy.

    Returns:
        Every exercise, keyed by id. Empty when the table has not been seeded.
    """
    global _CACHE
    if _CACHE is not None and not refresh:
        return _CACHE

    with Session(engine) as session:
        rows = session.exec(select(Exercise)).all()

    _CACHE = {row.id: _to_dict(row) for row in rows}
    logger.info("catalog_loaded", exercise_count=len(_CACHE))
    return _CACHE


def forbidden_joint_actions(profile: dict, contraindications: dict) -> set[str]:
    """Union the joint actions every declared injury forbids.

    Args:
        profile: User profile. Reads ``injuries``.
        contraindications: The ``contraindications`` rubric.

    Returns:
        Joint actions to exclude. Empty when no declared injury has a rubric
        entry — an unknown injury restricts nothing here, and the injury check
        reports it as unassessed rather than letting it read as cleared.
    """
    entries = contraindications["injuries"]
    return {
        action
        for injury in profile.get("injuries") or []
        if injury in entries
        for action in entries[injury]["avoid_joint_actions"]
    }


def forbidden_loaded_positions(profile: dict, contraindications: dict) -> set[str]:
    """Union the loaded positions every declared injury forbids.

    Args:
        profile: User profile. Reads ``injuries``.
        contraindications: The ``contraindications`` rubric.

    Returns:
        Loaded positions to exclude.
    """
    entries = contraindications["injuries"]
    return {
        position
        for injury in profile.get("injuries") or []
        if injury in entries
        for position in entries[injury].get("avoid_loaded_positions", [])
    }


def filter_candidates(
    slot: dict,
    profile: dict,
    catalog: dict[str, dict],
    forbidden_actions: set[str],
    forbidden_positions: set[str],
    exclude_ids: set[str] | None = None,
    limit: int = 8,
) -> list[dict]:
    """Return exercises that legitimately fill one template slot.

    Four filters, none of them skippable and none of them advisory:

    * the movement pattern matches the slot
    * the exercise's equipment is a subset of what the user has
    * its skill level is at or below the user's
    * none of its joint actions or loaded positions is contraindicated

    Args:
        slot: Template slot. Reads ``pattern``.
        profile: User profile. Reads ``equipment`` and ``level``.
        catalog: The catalog, keyed by id.
        forbidden_actions: Joint actions the user's injuries rule out.
        forbidden_positions: Loaded positions the user's injuries rule out.
        exclude_ids: Exercises already used, to avoid repeating one across days.
        limit: Maximum candidates to return.

    Returns:
        Up to ``limit`` candidates, cheapest-fatigue first so a tie between
        otherwise equal options resolves toward the more recoverable one. Empty
        when nothing qualifies — the caller must treat that as a conflicting
        constraint to report, not as permission to relax a filter.
    """
    available = set(profile.get("equipment") or [])
    # `or 1` rather than a dict default: an unanswered level reads as `None`
    # from the profile, and `None` here would raise on the comparison below.
    # `build_plan` asks for level, so this floor is a guard, not the norm.
    level = profile.get("level") or 1
    excluded = exclude_ids or set()

    candidates = [
        exercise
        for exercise in catalog.values()
        if exercise["exercise_id"] not in excluded
        and exercise["movement_pattern"] == slot["pattern"]
        and set(exercise["equipment"]) <= available
        and exercise["skill_level"] <= level
        and not set(exercise["joint_actions"]) & forbidden_actions
        and not set(exercise["loaded_positions"]) & forbidden_positions
    ]
    candidates.sort(key=lambda exercise: (exercise["fatigue_cost"], exercise["name"]))

    if not candidates:
        logger.info(
            "catalog_no_candidates_for_slot",
            slot_id=slot.get("slot_id"),
            pattern=slot.get("pattern"),
            equipment_count=len(available),
            forbidden_action_count=len(forbidden_actions),
        )
    return candidates[:limit]


def candidates_for_slot(
    slot: dict,
    profile: dict,
    catalog: dict[str, dict],
    forbidden_actions: set[str],
    forbidden_positions: set[str],
    used_ids: set[str] | None = None,
    limit: int = 8,
) -> list[dict]:
    """Return candidates for a slot, preferring exercises not already used.

    This is what ``choose_exercises`` and ``repair`` call. It exists because
    avoiding repeats across the week is a *preference*, while equipment,
    skill and contraindications are *constraints*. Treating the preference as a
    constraint makes plans unbuildable: a pattern with one qualifying exercise
    strands its second slot, and the catalog has several such patterns.

    So the exclusion is dropped when honouring it would leave nothing. The
    safety filters are never dropped — if ``filter_candidates`` returns empty
    before any exclusion, that is a genuine conflict and it stays empty.

    Args:
        slot: Template slot. Reads ``pattern`` and ``slot_id``.
        profile: User profile.
        catalog: The catalog, keyed by id.
        forbidden_actions: Joint actions the user's injuries rule out.
        forbidden_positions: Loaded positions the user's injuries rule out.
        used_ids: Exercises already placed in this plan.
        limit: Maximum candidates to return.

    Returns:
        Up to ``limit`` candidates. Empty only when the hard filters exclude
        everything, which the caller must report rather than work around.
    """
    preferred = filter_candidates(
        slot, profile, catalog, forbidden_actions, forbidden_positions, used_ids, limit
    )
    if preferred or not used_ids:
        return preferred

    fallback = filter_candidates(
        slot, profile, catalog, forbidden_actions, forbidden_positions, None, limit
    )
    if fallback:
        logger.info(
            "catalog_repeating_exercise_for_slot",
            slot_id=slot.get("slot_id"),
            pattern=slot.get("pattern"),
            reason="no unused exercise qualifies for this pattern",
        )
    return fallback


__all__ = [
    "candidates_for_slot",
    "filter_candidates",
    "forbidden_joint_actions",
    "forbidden_loaded_positions",
    "load_catalog",
]
