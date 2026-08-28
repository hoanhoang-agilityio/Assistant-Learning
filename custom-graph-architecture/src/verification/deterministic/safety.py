"""Safety constraints.

The injury gate, checked from both sides. An injury restricts movement patterns, and the
catalogue marks exercises contraindicated for body parts; the two do not cover the same
ground, so a plan has to clear both. A ``PROHIBITED`` restriction and a contraindication
are errors. A ``LIMITED`` one is a warning: the user may still train the movement with
care, and failing the plan over it three times would leave them with no plan at all.

Prescriptions whose ``exercise_id`` resolves to nothing are skipped rather than reported —
an invented exercise is task 5.1's finding, and there is no catalogue row here to judge.
"""

from src.core.langgraph.verification.deterministic.context import PlanContext
from src.enums import (
    MovementPattern,
    RestrictionAction,
)
from src.schemas import (
    CheckName,
    Exercise,
    Injury,
    MovementRestriction,
    PlanDay,
    PlannedExercise,
    Severity,
    VerificationIssue,
)

# Strictest first, so the worst restriction on a pattern is the one that gets reported.
_ACTION_ORDER: dict[RestrictionAction, int] = {
    RestrictionAction.PROHIBITED: 0,
    RestrictionAction.LIMITED: 1,
    RestrictionAction.ALLOWED: 2,
}

_REPLACE_PATTERN = "Replace it with an exercise that avoids that pattern."
_REPLACE_EXERCISE = "Replace it with one the catalogue does not flag for that injury."


def _because(restriction: MovementRestriction) -> str:
    """The reason an injury gives for a restriction, as a trailing clause."""

    return f" ({restriction.reason})" if restriction.reason else ""


def _restriction_on(
    injury: Injury, movement_pattern: MovementPattern
) -> MovementRestriction | None:
    """The strictest restriction an injury places on a movement pattern, if any."""

    return min(
        (
            restriction
            for restriction in injury.restrictions
            if restriction.movement_pattern is movement_pattern
        ),
        key=lambda restriction: _ACTION_ORDER[restriction.action],
        default=None,
    )


def _finding(exercise: Exercise, injury: Injury) -> tuple[Severity, str] | None:
    """What one injury has against one exercise: the single worst of it, or nothing.

    An exercise can be both contraindicated and restricted, and either way the fix is the
    same swap — so one injury is worth at most one issue, not a pile of them.
    """

    pattern = exercise.movement_pattern
    restriction = _restriction_on(injury, pattern)

    if restriction is not None and restriction.action is RestrictionAction.PROHIBITED:
        return Severity.ERROR, (
            f"{exercise.name} is a {pattern.value} movement, which the user's "
            f"{injury.body_part} injury rules out{_because(restriction)}. {_REPLACE_PATTERN}"
        )

    if exercise.is_contraindicated_for(injury.body_part):
        return Severity.ERROR, (
            f"{exercise.name} is contraindicated for the user's {injury.body_part} "
            f"injury. {_REPLACE_EXERCISE}"
        )

    if restriction is not None and restriction.action is RestrictionAction.LIMITED:
        return Severity.WARNING, (
            f"{exercise.name} is a {pattern.value} movement, which the user's "
            f"{injury.body_part} injury limits{_because(restriction)}. Keep it only with "
            f"conservative load and range, or replace it."
        )

    return None


def _check_prescription(
    context: PlanContext, day: PlanDay, prescribed: PlannedExercise
) -> list[VerificationIssue]:
    """Every injury finding against one prescription."""

    exercise = context.exercise_for(prescribed.exercise_id)
    if exercise is None:
        return []

    issues = []
    for injury in context.profile.active_injuries:
        finding = _finding(exercise, injury)
        if finding is None:
            continue
        severity, message = finding
        issues.append(
            VerificationIssue(
                check=CheckName.SAFETY,
                message=message,
                severity=severity,
                day_number=day.day_number,
                slot_id=prescribed.slot_id,
                exercise_id=prescribed.exercise_id,
            )
        )

    return issues


def check_safety(context: PlanContext) -> list[VerificationIssue]:
    """Check nothing the plan prescribes is ruled out by the user's injuries."""

    if not context.profile.active_injuries:
        return []

    return [
        issue
        for day in context.plan.training_days
        for prescribed in day.exercises
        for issue in _check_prescription(context, day, prescribed)
    ]
