"""Injury check: contraindicated movements given the user's declared injuries.

Injuries map to forbidden **attributes** — joint actions and loaded positions —
never to a list of exercise names. With a name list,
adding ``hack_squat`` to the catalog tomorrow slips straight through. With an
attribute intersection, every new exercise is assessed correctly the day it is
added, because the rule is a set operation over metadata the catalog already
carries.

This check runs even though ``filter_candidates`` already excluded
contraindicated exercises at build time: ``patch_plan`` and ``ingest_plan``
introduce exercises without ever passing through that filter.

No LLM in this module.

A caution on what this can and cannot do: ``"knee pain"`` as the user typed
it is not a diagnosis. The rubric assumes patellofemoral pain, and if the real
problem is a meniscus tear the "safe alternative" may also be wrong. That is why
the default severity is restrictive and why the composed answer must say this is
an exercise-selection adjustment, not medical advice.
"""

from collections import defaultdict

from app.schemas.graph import Issue

_MAX_ALTERNATIVES = 3


def check_injury(plan: dict, profile: dict, catalog: dict, rubric: dict) -> list[Issue]:
    """Flag exercises contraindicated by the user's declared injuries.

    Args:
        plan: The plan to assess.
        profile: User profile. Reads ``injuries`` as a list of rubric keys.
        catalog: Exercise metadata keyed by ``exercise_id``.
        rubric: The ``contraindications`` rubric.

    Returns:
        One issue per contraindicated exercise plus any exceeded pattern limits.
        Empty when the user declared no injuries.
    """
    injuries = profile.get("injuries") or []
    if not injuries:
        return []

    entries = rubric["injuries"]
    known = [injury for injury in injuries if injury in entries]

    issues: list[Issue] = [
        _issue(
            "info",
            "Profile",
            f"'{injury}' has no entry in the contraindication rubric, so it was not "
            "assessed. Nothing here accounts for it.",
            "contraindications",
        )
        for injury in injuries
        if injury not in entries
    ]
    if not known:
        return issues

    forbidden_actions = {
        action for injury in known for action in entries[injury]["avoid_joint_actions"]
    }
    forbidden_positions = {
        position
        for injury in known
        for position in entries[injury].get("avoid_loaded_positions", [])
    }
    rubric_ref = f"contraindications.{known[0]}"

    issues.extend(
        _check_exercises(plan, catalog, forbidden_actions, forbidden_positions, rubric_ref)
    )
    issues.extend(_check_pattern_limits(plan, catalog, entries, known))
    return issues


def _check_exercises(
    plan: dict,
    catalog: dict,
    forbidden_actions: set[str],
    forbidden_positions: set[str],
    rubric_ref: str,
) -> list[Issue]:
    """Intersect each exercise's attributes with the forbidden sets."""
    issues: list[Issue] = []

    for index, day in enumerate(plan.get("days") or []):
        day_name = day.get("name") or f"Day {index + 1}"
        for exercise in day.get("exercises") or []:
            exercise_id = exercise.get("exercise_id")
            meta = catalog.get(exercise_id)
            if meta is None:
                issues.append(
                    _issue(
                        "info",
                        day_name,
                        f"'{exercise_id}' is not in the catalog, so it was not checked "
                        "against your injuries.",
                        "contraindications.catalog",
                    )
                )
                continue

            hits = set(meta.get("joint_actions") or []) & forbidden_actions
            hits |= set(meta.get("loaded_positions") or []) & forbidden_positions
            if not hits:
                continue

            issues.append(
                _issue(
                    "block",
                    f"{day_name} / {meta.get('name', exercise_id)}",
                    f"Contraindicated for your declared injury: {', '.join(sorted(hits))}.",
                    rubric_ref,
                    suggestion=_find_alternative(
                        meta, catalog, forbidden_actions, forbidden_positions
                    ),
                )
            )

    return issues


def _check_pattern_limits(
    plan: dict, catalog: dict, entries: dict, known: list[str]
) -> list[Issue]:
    """Flag movement patterns used beyond the weekly cap an injury imposes."""
    caps: dict[str, tuple[int, str]] = {}
    for injury in known:
        for limit in entries[injury].get("limit", []):
            pattern = limit["pattern"]
            cap = limit["max_sets_week"]
            # Most restrictive cap wins when two injuries limit the same pattern.
            if pattern not in caps or cap < caps[pattern][0]:
                caps[pattern] = (cap, injury)

    if not caps:
        return []

    weekly: defaultdict[str, float] = defaultdict(float)
    for day in plan.get("days") or []:
        for exercise in day.get("exercises") or []:
            meta = catalog.get(exercise.get("exercise_id"))
            if meta is None:
                continue
            weekly[meta.get("movement_pattern", "")] += exercise.get("sets") or 0

    return [
        _issue(
            "block",
            f"{pattern} pattern",
            f"{weekly[pattern]:.0f} sets/week of {pattern}, above the {cap}-set cap your "
            "declared injury imposes.",
            f"contraindications.{injury}.limit",
            suggestion={"max_sets_week": cap},
        )
        for pattern, (cap, injury) in sorted(caps.items())
        if weekly[pattern] > cap
    ]


def _find_alternative(
    meta: dict, catalog: dict, forbidden_actions: set[str], forbidden_positions: set[str]
) -> dict | None:
    """Find catalog exercises that train the same pattern without the forbidden attributes.

    An issue that only names a fault leaves ``repair`` nothing to act on, so a
    replacement is part of the finding rather than a separate lookup.

    Args:
        meta: Catalog entry of the offending exercise.
        catalog: Exercise metadata keyed by ``exercise_id``.
        forbidden_actions: Joint actions to avoid.
        forbidden_positions: Loaded positions to avoid.

    Returns:
        ``{"alternatives": [{"exercise_id": ..., "name": ...}, ...]}``, or
        ``None`` when the catalog offers nothing safe for this pattern.
    """
    pattern = meta.get("movement_pattern")
    alternatives = [
        {"exercise_id": exercise_id, "name": candidate.get("name", exercise_id)}
        for exercise_id, candidate in sorted(catalog.items())
        if candidate.get("movement_pattern") == pattern
        and candidate is not meta
        and not set(candidate.get("joint_actions") or []) & forbidden_actions
        and not set(candidate.get("loaded_positions") or []) & forbidden_positions
    ]
    return {"alternatives": alternatives[:_MAX_ALTERNATIVES]} if alternatives else None


def _issue(
    severity: str,
    location: str,
    message: str,
    rubric_ref: str,
    suggestion: dict | None = None,
) -> Issue:
    """Build an injury issue.

    Args:
        severity: ``"info"``, ``"warn"`` or ``"block"``.
        location: Where in the plan the issue is.
        message: User-facing explanation.
        rubric_ref: Dotted path of the rule that fired.
        suggestion: Replacement exercises, when the catalog offers any.

    Returns:
        The issue.
    """
    return Issue(
        source="injury",
        severity=severity,
        location=location,
        message=message,
        suggestion=suggestion,
        rubric_ref=rubric_ref,
    )
