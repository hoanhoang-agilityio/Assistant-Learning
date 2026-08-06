"""Describe what a pending change would do to the user's plan.

The diff is shown **against the plan the user currently has**, not against the
plan they are moving to. The question they are
answering at the confirm gate is "what am I about to lose?", and a diff written
the other way round does not answer it.

Deterministic: this is a comparison, and a model paraphrasing it could soften a
removal into something that reads like an addition.
"""

from typing import Any

# Macro movements smaller than this are rounding, not a change worth reporting.
_KCAL_NOISE = 20


def build_diff(
    current_plan: dict[str, Any] | None,
    draft_plan: dict[str, Any] | None,
    current_macros: dict[str, Any] | None,
    computed_macros: dict[str, Any] | None,
) -> dict[str, Any]:
    """Compare the pending plan against the approved one.

    Args:
        current_plan: The plan the user approved.
        draft_plan: The plan they would get.
        current_macros: Macros belonging to the approved plan.
        computed_macros: Macros for the pending plan.

    Returns:
        ``{"days_before", "days_after", "added", "removed", "kept",
        "macro_delta", "summary"}``. ``summary`` is a ready-to-show string.
    """
    before = _exercise_names(current_plan)
    after = _exercise_names(draft_plan)

    added = sorted(after - before)
    removed = sorted(before - after)
    days_before = len((current_plan or {}).get("days") or [])
    days_after = len((draft_plan or {}).get("days") or [])

    macro_delta = _macro_delta(current_macros, computed_macros)

    return {
        "days_before": days_before,
        "days_after": days_after,
        "added": added,
        "removed": removed,
        "kept": sorted(before & after),
        "macro_delta": macro_delta,
        "summary": _summary(days_before, days_after, added, removed, macro_delta),
    }


def _exercise_names(plan: dict[str, Any] | None) -> set[str]:
    """Collect the display names of every exercise in a plan.

    Names rather than ids because this text is shown to the user, and an id
    tells them nothing about what they are losing.

    Args:
        plan: The plan to read.

    Returns:
        Display names, empty when there is no plan.
    """
    return {
        exercise.get("name", exercise.get("exercise_id", "?"))
        for day in (plan or {}).get("days") or []
        for exercise in day.get("exercises") or []
    }


def _macro_delta(current: dict[str, Any] | None, pending: dict[str, Any] | None) -> dict[str, int]:
    """Compute the change in each macro target.

    Args:
        current: Macros belonging to the approved plan.
        pending: Macros for the pending plan.

    Returns:
        Field-to-delta for anything that moved by more than rounding. Empty when
        nothing meaningfully changed or one side is missing.
    """
    if not current or not pending:
        return {}

    delta: dict[str, int] = {}
    for field in ("kcal", "tdee", "protein_g", "fat_g", "carbs_g"):
        if field not in current or field not in pending:
            continue
        moved = pending[field] - current[field]
        threshold = _KCAL_NOISE if field in {"kcal", "tdee"} else 1
        if abs(moved) >= threshold:
            delta[field] = int(moved)
    return delta


def _summary(
    days_before: int,
    days_after: int,
    added: list[str],
    removed: list[str],
    macro_delta: dict[str, int],
) -> str:
    """Render the diff as the sentence shown at the confirm gate.

    Leads with what is lost. That ordering is deliberate: the user is being
    asked to approve overwriting something they already accepted, and the
    removals are the part they might not have expected.

    Args:
        days_before: Sessions in the approved plan.
        days_after: Sessions in the pending plan.
        added: Exercises being introduced.
        removed: Exercises being dropped.
        macro_delta: Macro movements worth reporting.

    Returns:
        A short human-readable summary.
    """
    parts: list[str] = []

    if days_before != days_after:
        parts.append(f"{days_before} → {days_after} sessions a week")

    if removed:
        parts.append(f"Removing: {', '.join(removed)}")
    if added:
        parts.append(f"Adding: {', '.join(added)}")

    if "kcal" in macro_delta:
        direction = "up" if macro_delta["kcal"] > 0 else "down"
        parts.append(f"Calories {direction} by {abs(macro_delta['kcal'])}/day")

    if not parts:
        return "Nothing about the plan would actually change."
    return ". ".join(parts) + "."


__all__ = ["build_diff"]
