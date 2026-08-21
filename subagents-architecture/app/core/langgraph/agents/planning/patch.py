"""Apply a requested change to an approved plan.

Deterministic. The classifier already decided *what* the user asked to change
and put it in ``changes``; turning that into a modified plan is a merge, and
there is nothing left for a model to judge.

Two rules shape this module:

**Modification must not become regeneration.** Routing a change back through
``build_plan`` would rebuild from scratch and quietly drop every exercise the
user has been happy with for six weeks. A patch keeps what still fits and
replaces only what the change forces.

**A patch cannot take a shortcut past the checks.** It produces a
``draft_plan`` and nothing else. Macros are recomputed and all three verifiers
re-run afterwards, because adding a session raises TDEE and breaks a deficit
that was correct before the change.
"""

from typing import Any

from app.core.langgraph.agents.planning.issues import make_planning_issue as _issue
from app.core.logging import logger
from app.schemas.graph import Issue
from app.services.catalog import (
    candidates_for_slot,
    forbidden_joint_actions,
    forbidden_loaded_positions,
)
from app.services.rubrics import contraindications
from app.services.templates import iter_slots, query_templates

# Change keys this module knows how to apply. Anything else is reported rather
# than silently ignored — a user who asks for something and gets an unchanged
# plan with no explanation has been told nothing.
SUPPORTED_CHANGES = frozenset({"days", "goal"})


def patch_plan(
    plan: dict[str, Any],
    changes: dict[str, Any],
    profile: dict[str, Any],
    catalog: dict[str, dict],
) -> tuple[dict[str, Any] | None, list[Issue]]:
    """Apply a change delta to an approved plan.

    Args:
        plan: The plan the user already approved.
        changes: Delta from the classifier, e.g. ``{"days": 5}``.
        profile: User profile, for re-filtering any newly needed slots.
        catalog: Exercise metadata keyed by id.

    Returns:
        ``(draft_plan, issues)``. ``draft_plan`` is ``None`` when the change
        cannot be applied at all, in which case ``issues`` explains why.
    """
    if not plan:
        return None, [
            _issue(
                "block",
                "Plan",
                "There is no saved plan to change yet.",
                "change.no_plan",
            )
        ]

    unsupported = sorted(set(changes) - SUPPORTED_CHANGES)
    if unsupported:
        return None, [
            _issue(
                "block",
                "Change request",
                f"I can't apply that change yet ({', '.join(unsupported)}). "
                f"I can change the number of training days or the goal.",
                "change.unsupported",
            )
        ]

    if not changes:
        return None, [
            _issue(
                "block",
                "Change request",
                "I couldn't tell what you wanted changed. Say what to adjust — "
                "for example the number of days a week.",
                "change.empty",
            )
        ]

    # A goal change alters nothing structural: the same sessions are trained,
    # and `calc_macro` recomputes the targets downstream.
    if "days" not in changes:
        logger.info("patch_plan_macros_only", changes=sorted(changes))
        return dict(plan), []

    return _change_day_count(plan, int(changes["days"]), profile, catalog)


def _change_day_count(
    plan: dict[str, Any], days: int, profile: dict[str, Any], catalog: dict[str, dict]
) -> tuple[dict[str, Any] | None, list[Issue]]:
    """Move a plan onto a template with a different number of days.

    Exercises the user already has are carried into any slot of the same
    movement pattern, so a 4→5 day change reads as an added session rather than
    a different programme.

    Args:
        plan: The approved plan.
        days: The requested sessions per week.
        profile: User profile.
        catalog: Exercise metadata keyed by id.

    Returns:
        ``(draft_plan, issues)``.
    """
    goal = profile.get("goal", "general_health")
    level = profile.get("level", 1)

    matches = query_templates(days_per_week=days, goal=goal, level=level)
    if not matches:
        return None, [
            _issue(
                "block",
                "Programme",
                f"No programme template runs {days} sessions a week for a {goal} goal. "
                "Your current plan is unchanged.",
                "templates.no_match",
            )
        ]

    template = matches[0]
    carried = _exercises_by_pattern(plan, catalog)

    forbidden_actions = forbidden_joint_actions(profile, contraindications())
    forbidden_positions = forbidden_loaded_positions(profile, contraindications())

    issues: list[Issue] = []
    by_day: dict[str, list[dict]] = {}
    reused = 0

    for slot in iter_slots(template):
        exercise_id = carried.get(slot["pattern"])

        # A carried exercise is re-checked, never trusted. The profile may have
        # gained an injury since the plan was approved, and carrying an exercise
        # forward is exactly how a contraindicated one would survive.
        if exercise_id is not None and not _is_allowed(
            exercise_id, catalog, forbidden_actions, forbidden_positions
        ):
            exercise_id = None

        if exercise_id is None:
            candidates = candidates_for_slot(
                slot, profile, catalog, forbidden_actions, forbidden_positions
            )
            if not candidates:
                issues.append(
                    _issue(
                        "warn",
                        f"{slot['day_name']} / {slot['pattern'].replace('_', ' ')}",
                        "Nothing safe and available fills this slot, so it was left out.",
                        "catalog.no_candidates",
                    )
                )
                continue
            exercise_id = candidates[0]["exercise_id"]
        else:
            reused += 1

        by_day.setdefault(slot["day_name"], []).append(
            {
                "slot_id": slot["slot_id"],
                "exercise_id": exercise_id,
                "name": catalog[exercise_id]["name"],
                "sets": slot["sets"],
                "reps": slot["reps"],
                "rir": slot["rir"],
            }
        )

    draft = {
        "template_id": template["template_id"],
        "days": [
            {"name": day["name"], "exercises": by_day[day["name"]]}
            for day in template["days"]
            if day["name"] in by_day
        ],
    }

    logger.info(
        "patch_plan_day_count_changed",
        days=days,
        template_id=template["template_id"],
        exercises_reused=reused,
        slots_dropped=len(issues),
    )
    return draft, issues


def _exercises_by_pattern(plan: dict[str, Any], catalog: dict[str, dict]) -> dict[str, str]:
    """Index the plan's exercises by the movement pattern they fill.

    Args:
        plan: The approved plan.
        catalog: Exercise metadata keyed by id.

    Returns:
        ``pattern -> exercise_id``, first occurrence wins.
    """
    found: dict[str, str] = {}
    for day in plan.get("days") or []:
        for exercise in day.get("exercises") or []:
            meta = catalog.get(exercise.get("exercise_id"))
            if meta is None:
                continue
            found.setdefault(meta["movement_pattern"], exercise["exercise_id"])
    return found


def _is_allowed(
    exercise_id: str,
    catalog: dict[str, dict],
    forbidden_actions: set[str],
    forbidden_positions: set[str],
) -> bool:
    """Re-check a carried exercise against the current contraindications.

    Args:
        exercise_id: The exercise being carried forward.
        catalog: Exercise metadata keyed by id.
        forbidden_actions: Joint actions the user's injuries rule out.
        forbidden_positions: Loaded positions the user's injuries rule out.

    Returns:
        ``True`` when the exercise is still safe for this user.
    """
    meta = catalog.get(exercise_id)
    if meta is None:
        return False
    return not (
        set(meta["joint_actions"]) & forbidden_actions
        or set(meta["loaded_positions"]) & forbidden_positions
    )


__all__ = ["SUPPORTED_CHANGES", "patch_plan"]
