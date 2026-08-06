"""Volume check: weekly set counts, frequency and session length.

Set counts are fractional. One set of bench contributes 1.0 to chest and 0.5 to
triceps and front delts, per the catalog's ``contribution`` map — counting it as
one whole set for every muscle it touches inflates every total.

A muscle group with no landmark entry produces an ``info`` issue saying it was
not assessed. Silently passing an unlisted group would read as approval.
"""

from collections import defaultdict

from app.schemas.graph import Issue


def check_volume(plan: dict, catalog: dict, rubric: dict) -> list[Issue]:
    """Assess weekly volume, frequency and session length.

    Args:
        plan: The plan to assess.
        catalog: Exercise metadata keyed by ``exercise_id``.
        rubric: The ``volume_landmarks`` rubric.

    Returns:
        One issue per violated rule, empty when everything passes.
    """
    days = plan.get("days") or []
    if not days:
        return [_issue("info", "Plan", "The plan has no training days to assess.", "volume")]

    weekly_sets: defaultdict[str, float] = defaultdict(float)
    weekly_days: defaultdict[str, set[int]] = defaultdict(set)
    issues: list[Issue] = []

    for index, day in enumerate(days):
        issues.extend(_check_session(day, catalog, rubric))
        for exercise in day.get("exercises") or []:
            meta = catalog.get(exercise.get("exercise_id"))
            if meta is None:
                issues.append(
                    _issue(
                        "info",
                        _day_name(day, index),
                        f"'{exercise.get('exercise_id')}' is not in the catalog, so its "
                        "volume was not counted.",
                        "volume.catalog",
                    )
                )
                continue
            sets = exercise.get("sets") or 0
            for muscle, share in (meta.get("contribution") or {}).items():
                weekly_sets[muscle] += sets * share
                if sets * share > 0:
                    weekly_days[muscle].add(index)

    issues.extend(_check_weekly_sets(weekly_sets, rubric))
    issues.extend(_check_frequency(weekly_days, rubric))
    return issues


def _check_weekly_sets(weekly_sets: dict[str, float], rubric: dict) -> list[Issue]:
    """Compare each muscle's weekly set total against its landmarks."""
    landmarks = rubric["muscles"]
    issues: list[Issue] = []

    for muscle, total in sorted(weekly_sets.items()):
        entry = landmarks.get(muscle)
        if entry is None:
            issues.append(
                _issue(
                    "info",
                    muscle,
                    f"{total:.1f} sets/week. No volume landmark is defined for this muscle, "
                    "so it was not assessed.",
                    "volume.muscles",
                )
            )
            continue

        if total > entry["mrv"]:
            issues.append(
                _issue(
                    "block",
                    muscle,
                    f"{total:.1f} sets/week exceeds MRV ({entry['mrv']}). More than this is "
                    "fatigue you cannot recover from.",
                    f"volume.{muscle}.mrv",
                    suggestion={"target_sets_week": entry["mav"][1]},
                )
            )
        elif total < entry["mev"]:
            issues.append(
                _issue(
                    "warn",
                    muscle,
                    f"{total:.1f} sets/week is below MEV ({entry['mev']}) — likely too little "
                    "to drive growth.",
                    f"volume.{muscle}.mev",
                    suggestion={"target_sets_week": entry["mav"][0]},
                )
            )

    return issues


def _check_frequency(weekly_days: dict[str, set[int]], rubric: dict) -> list[Issue]:
    """Flag muscles trained too rarely or too often across the week.

    Muscles whose landmark sets ``mev`` to 0 are skipped. A zero MEV is the
    rubric saying no *direct* work is required — the muscle gets what it needs
    from compounds — so demanding a minimum weekly frequency for it contradicts
    the same rubric and fills the report with warnings about forearms.
    """
    rule = rubric["frequency"]
    landmarks = rubric["muscles"]
    issues: list[Issue] = []

    for muscle, days in sorted(weekly_days.items()):
        entry = landmarks.get(muscle)
        if entry is not None and entry["mev"] == 0:
            continue

        count = len(days)
        if count < rule["min_per_week"]:
            issues.append(
                _issue(
                    "warn",
                    muscle,
                    f"Trained {count}x/week, below the {rule['min_per_week']}x minimum.",
                    "volume.frequency.min_per_week",
                )
            )
        elif count > rule["max_per_week"]:
            issues.append(
                _issue(
                    "warn",
                    muscle,
                    f"Trained {count}x/week, above the {rule['max_per_week']}x maximum.",
                    "volume.frequency.max_per_week",
                )
            )

    return issues


def _check_session(day: dict, catalog: dict, rubric: dict) -> list[Issue]:
    """Flag a session that is too long or too concentrated on one muscle."""
    rule = rubric["session"]
    name = _day_name(day, 0)
    exercises = day.get("exercises") or []

    total_sets = sum(exercise.get("sets") or 0 for exercise in exercises)
    issues: list[Issue] = []

    if total_sets > rule["max_sets"]:
        issues.append(
            _issue(
                "warn",
                name,
                f"{total_sets} sets in one session, above the {rule['max_sets']} cap. "
                "Quality drops well before the end.",
                "volume.session.max_sets",
            )
        )

    per_muscle: defaultdict[str, float] = defaultdict(float)
    for exercise in exercises:
        meta = catalog.get(exercise.get("exercise_id"))
        if meta is None:
            continue
        for muscle, share in (meta.get("contribution") or {}).items():
            per_muscle[muscle] += (exercise.get("sets") or 0) * share

    cap = rule["max_hard_sets_per_muscle"]
    for muscle, total in sorted(per_muscle.items()):
        if total > cap:
            issues.append(
                _issue(
                    "warn",
                    f"{name} / {muscle}",
                    f"{total:.1f} sets for one muscle in a single session, above the {cap} cap.",
                    "volume.session.max_hard_sets_per_muscle",
                )
            )

    return issues


def _day_name(day: dict, index: int) -> str:
    """Return a day's display name, falling back to its position."""
    return day.get("name") or f"Day {index + 1}"


def _issue(
    severity: str,
    location: str,
    message: str,
    rubric_ref: str,
    suggestion: dict | None = None,
) -> Issue:
    """Build a volume issue.

    Args:
        severity: ``"info"``, ``"warn"`` or ``"block"``.
        location: Where in the plan the issue is, e.g. ``"Push A / chest"``.
        message: User-facing explanation.
        rubric_ref: Dotted path of the rule that fired.
        suggestion: Replacement values, when there is a concrete fix.

    Returns:
        The issue.
    """
    return Issue(
        source="volume",
        severity=severity,
        location=location,
        message=message,
        suggestion=suggestion,
        rubric_ref=rubric_ref,
    )
