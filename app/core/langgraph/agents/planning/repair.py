"""Repair a plan the verifiers rejected.

``repair_plan`` takes no ``messages`` parameter, for the same reason
``VerifyState`` has no ``messages`` field. A repairer
that can read the build transcript starts justifying the plan it already made
instead of fixing it. Here the rule is enforced by the function signature — the
transcript is not available to pass in.

Repairs are deterministic. Every issue that blocks carries a ``suggestion``
produced by the check that raised it, and the replacement is re-selected through
``candidates_for_slot``, so a repair cannot introduce an exercise the user's
equipment, level or injuries exclude. No model is involved: with a suggestion
already attached, there is nothing left to decide.
"""

from typing import Any

from app.core.langgraph.rubrics import CONTRAINDICATIONS
from app.core.langgraph.templates import get_template, iter_slots
from app.core.logging import logger
from app.schemas.graph import Issue
from app.services.catalog import (
    candidates_for_slot,
    forbidden_joint_actions,
    forbidden_loaded_positions,
)

# Repairs only address findings that block. A warning is a judgment call the
# user is entitled to overrule, and spending the repair budget on one would
# leave a real violation unfixed.
_REPAIRABLE_SEVERITY = "block"


def repair_plan(
    draft_plan: dict[str, Any],
    issues: list[Issue],
    profile: dict[str, Any],
    catalog: dict[str, dict],
) -> tuple[dict[str, Any], int]:
    """Replace exercises that caused blocking issues.

    Args:
        draft_plan: The plan the verifiers rejected.
        issues: Everything they found this round.
        profile: User profile, for re-filtering replacements.
        catalog: Exercise metadata keyed by id.

    Returns:
        ``(repaired_plan, swap_count)``. A swap count of 0 means nothing could
        be improved — the caller must stop rather than loop, since another pass
        would produce the same plan.
    """
    blocking = [issue for issue in issues if issue["severity"] == _REPAIRABLE_SEVERITY]
    if not blocking:
        return draft_plan, 0

    template = get_template(draft_plan.get("template_id", ""))
    slots_by_id = {slot["slot_id"]: slot for slot in iter_slots(template)} if template else {}

    forbidden_actions = forbidden_joint_actions(profile, CONTRAINDICATIONS)
    forbidden_positions = forbidden_loaded_positions(profile, CONTRAINDICATIONS)

    offending = _offending_exercise_ids(draft_plan, blocking, catalog)
    if not offending:
        logger.info("repair_no_actionable_issues", blocking=len(blocking))
        return draft_plan, 0

    used = {
        exercise["exercise_id"]
        for day in draft_plan.get("days") or []
        for exercise in day.get("exercises") or []
    }

    repaired_days: list[dict] = []
    swaps = 0

    for day in draft_plan.get("days") or []:
        exercises: list[dict] = []
        for exercise in day.get("exercises") or []:
            if exercise["exercise_id"] not in offending:
                exercises.append(exercise)
                continue

            slot = slots_by_id.get(exercise["slot_id"])
            replacement = _pick_replacement(
                slot, profile, catalog, forbidden_actions, forbidden_positions, used
            )
            if replacement is None:
                # Nothing safe fills this slot. Keep the exercise so the plan
                # stays complete and the issue is reported to the user, rather
                # than silently producing a shorter session.
                logger.info(
                    "repair_no_replacement_available",
                    slot_id=exercise["slot_id"],
                    exercise_id=exercise["exercise_id"],
                )
                exercises.append(exercise)
                continue

            used.discard(exercise["exercise_id"])
            used.add(replacement)
            swaps += 1
            logger.info(
                "repair_exercise_swapped",
                slot_id=exercise["slot_id"],
                was=exercise["exercise_id"],
                now=replacement,
            )
            # Sets, reps and RIR are the template's and never move: the plan was
            # rejected for *which* exercise it used, not for its prescription.
            exercises.append(
                {**exercise, "exercise_id": replacement, "name": catalog[replacement]["name"]}
            )

        repaired_days.append({**day, "exercises": exercises})

    logger.info("repair_completed", swaps=swaps, blocking_issues=len(blocking))
    return {**draft_plan, "days": repaired_days}, swaps


def _offending_exercise_ids(
    draft_plan: dict[str, Any], blocking: list[Issue], catalog: dict[str, dict]
) -> set[str]:
    """Map blocking issues back to the exercises that caused them.

    Issues name a location like ``"Lower A / Barbell back squat"`` rather than an
    id, so the display name is matched against the plan's exercises.

    Args:
        draft_plan: The rejected plan.
        blocking: Issues with severity ``block``.
        catalog: Exercise metadata keyed by id.

    Returns:
        Ids of the exercises to replace. Empty when the blocking issues are
        about the plan as a whole (macros, weekly volume) rather than about a
        specific movement — those are not fixed by swapping an exercise.
    """
    locations = " || ".join(issue["location"] for issue in blocking)
    return {
        exercise["exercise_id"]
        for day in draft_plan.get("days") or []
        for exercise in day.get("exercises") or []
        if exercise["exercise_id"] in catalog
        and catalog[exercise["exercise_id"]]["name"] in locations
    }


def _pick_replacement(
    slot: dict | None,
    profile: dict[str, Any],
    catalog: dict[str, dict],
    forbidden_actions: set[str],
    forbidden_positions: set[str],
    used: set[str],
) -> str | None:
    """Choose a safe replacement for one slot.

    Goes back through ``candidates_for_slot`` rather than trusting the issue's
    suggestion directly, so the replacement is re-checked against equipment,
    skill level and every contraindication — a repair must not be a way around
    the filter that caused it.

    Args:
        slot: The template slot being refilled.
        profile: User profile.
        catalog: Exercise metadata keyed by id.
        forbidden_actions: Joint actions the user's injuries rule out.
        forbidden_positions: Loaded positions the user's injuries rule out.
        used: Exercises already in the plan.

    Returns:
        A replacement exercise id, or ``None`` when nothing safe qualifies.
    """
    if slot is None:
        return None

    candidates = candidates_for_slot(
        slot, profile, catalog, forbidden_actions, forbidden_positions, used_ids=used
    )
    return candidates[0]["exercise_id"] if candidates else None


__all__ = ["repair_plan"]
