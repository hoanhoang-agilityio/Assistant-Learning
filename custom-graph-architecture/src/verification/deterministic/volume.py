"""Training volume and schedule.

Whether the week is trainable. This rule reads the plan against the *profile*, where task
5.1 reads it against the template: the plan trains the days a week the user says they can,
and the prescribed work stays inside bounds a person could actually complete.

The bounds below are outer limits, not targets. The gate exists to catch a week nobody
could run, not to argue programming with the coach — so a plan is failed for volume only
where the number is outside anything a reasonable coach would write, and merely flagged
where it disagrees with what the template asked for.
"""

import re
from collections import Counter

from src.enums import MuscleGroup
from src.schemas import (
    CheckName,
    ExerciseSlot,
    PlanDay,
    PlannedExercise,
    Severity,
    TrainingPlan,
    UserProfile,
    VerificationIssue,
    WorkoutTemplate,
)
from src.verification.deterministic.context import PlanContext

# Working sets per muscle per week. The productive band in the training literature sits
# around 10-20 sets; this is the far edge of it. Sets are counted where a muscle is primary
# — counting every secondary would put half the ceiling on arm work the coach never
# prescribed directly.
MAX_WEEKLY_SETS_PER_MUSCLE = 30

# How far under the template's own weekly sets for a muscle the plan may fall before it is
# worth mentioning. There is no absolute floor here on purpose: a two-day week gives every
# muscle a handful of sets by construction, and a fixed minimum would flag every low
# frequency template as underdone. The template already said what it wanted.
WEEKLY_SETS_SHORTFALL = 0.5

# One session's total working sets. Past this a session stops fitting in an evening.
MAX_SETS_PER_DAY = 30

# Sets of one exercise in one session.
MAX_SETS_PER_EXERCISE = 10

# Reps a person performs as prescribed. The wide ceiling is deliberate: high-rep work is a
# real choice, and three digits is a typo.
MIN_REPS = 1
MAX_REPS = 50

# The format PlannedExercise.reps documents: "10" or "8-12".
_REPS = re.compile(r"^\s*(\d+)\s*(?:-\s*(\d+))?\s*$")


def _issue(
    message: str, severity: Severity = Severity.ERROR, **location: object
) -> VerificationIssue:
    """One volume issue, located as precisely as the check that found it can manage."""

    return VerificationIssue(
        check=CheckName.VOLUME, message=message, severity=severity, **location
    )


def _sets(count: int) -> str:
    """A set count as it should read in a sentence."""

    return f"{count} working set{'' if count == 1 else 's'}"


def _parse_reps(reps: str) -> tuple[int, int] | None:
    """A rep prescription as its low and high bound, or None when it does not parse."""

    match = _REPS.match(reps)
    if match is None:
        return None

    low = int(match.group(1))
    high = int(match.group(2)) if match.group(2) is not None else low
    return (low, high) if low <= high else None


def _check_schedule(
    plan: TrainingPlan, profile: UserProfile
) -> list[VerificationIssue]:
    """Check the plan trains as many days a week as the user said they could.

    A warning, not a failure: ``find_template`` picks the template closest to the requested
    week and the catalogue may hold no exact match, so the coach can be handed a five-day
    template by a user who asked for four. Failing that would bounce a plan the coach had
    no way to write differently, three times, and leave the user with nothing.
    """

    planned = len(plan.training_days)
    requested = profile.training_days_per_week
    if planned == requested:
        return []

    return [
        _issue(
            f"The plan trains {planned} days a week; the user said they can train "
            f"{requested}. Use a template that matches if the catalogue has one.",
            severity=Severity.WARNING,
            field="training_days",
        )
    ]


def _check_reps(
    day: PlanDay, prescribed: PlannedExercise, slot: ExerciseSlot | None
) -> list[VerificationIssue]:
    """Check the rep prescription reads as a number and asks for a human number of them."""

    location = {
        "day_number": day.day_number,
        "slot_id": prescribed.slot_id,
        "exercise_id": prescribed.exercise_id,
        "field": "reps",
    }

    parsed = _parse_reps(prescribed.reps)
    if parsed is None:
        return [
            _issue(
                f"'{prescribed.reps}' is not a rep prescription. Write a number or a "
                f"range, as in '10' or '8-12'.",
                **location,
            )
        ]

    low, high = parsed
    if low < MIN_REPS or high > MAX_REPS:
        return [
            _issue(
                f"{prescribed.reps} reps is outside {MIN_REPS}-{MAX_REPS}. Prescribe a "
                f"number of reps a person performs.",
                **location,
            )
        ]

    # The slot's range is what the template asked for; a coach may reasonably shade it, so
    # only a prescription that misses it entirely is worth mentioning.
    if slot is not None and slot.rep_range is not None:
        wanted_low, wanted_high = slot.rep_range
        if high < wanted_low or low > wanted_high:
            return [
                _issue(
                    f"{prescribed.reps} reps falls outside the {wanted_low}-{wanted_high} "
                    f"range slot '{prescribed.slot_id}' asks for.",
                    severity=Severity.WARNING,
                    **location,
                )
            ]

    return []


def _check_sets(
    day: PlanDay, prescribed: PlannedExercise, slot: ExerciseSlot | None
) -> list[VerificationIssue]:
    """Check one exercise's sets are trainable, and are what the template asked for."""

    location = {
        "day_number": day.day_number,
        "slot_id": prescribed.slot_id,
        "exercise_id": prescribed.exercise_id,
        "field": "sets",
    }

    if prescribed.sets > MAX_SETS_PER_EXERCISE:
        return [
            _issue(
                f"{prescribed.sets} sets of one exercise is past the "
                f"{MAX_SETS_PER_EXERCISE} this plan allows. Spread the work or cut it.",
                **location,
            )
        ]

    if slot is not None and slot.sets is not None and prescribed.sets != slot.sets:
        return [
            _issue(
                f"Slot '{prescribed.slot_id}' asks for {slot.sets} sets and the plan "
                f"prescribes {prescribed.sets}.",
                severity=Severity.WARNING,
                **location,
            )
        ]

    return []


def _check_day_volume(day: PlanDay) -> list[VerificationIssue]:
    """Check a single session is not longer than an evening."""

    total = sum(prescribed.sets for prescribed in day.exercises)
    if total <= MAX_SETS_PER_DAY:
        return []

    return [
        _issue(
            f"Day {day.day_number} prescribes {_sets(total)}, past the "
            f"{MAX_SETS_PER_DAY} this plan allows. Drop exercises or sets.",
            day_number=day.day_number,
        )
    ]


def _weekly_sets(context: PlanContext) -> Counter[MuscleGroup]:
    """Working sets per muscle across the week, counted where the muscle is primary."""

    weekly: Counter[MuscleGroup] = Counter()
    for day in context.plan.training_days:
        for prescribed in day.exercises:
            exercise = context.exercise_for(prescribed.exercise_id)
            if exercise is None:
                continue
            for muscle in exercise.primary_muscles:
                weekly[muscle] += prescribed.sets

    return weekly


def _template_weekly_sets(template: WorkoutTemplate) -> Counter[MuscleGroup]:
    """The weekly sets per muscle the template itself asks for."""

    wanted: Counter[MuscleGroup] = Counter()
    for slot in template.slots():
        if slot.sets is None:
            continue
        for muscle in slot.target_muscles:
            wanted[muscle] += slot.sets

    return wanted


def _check_weekly_volume(
    weekly: Counter[MuscleGroup], template: WorkoutTemplate | None
) -> list[VerificationIssue]:
    """Check no muscle is buried, and none the template set out to train was skipped."""

    issues = [
        _issue(
            f"{muscle.value} gets {_sets(sets)} a week, past the "
            f"{MAX_WEEKLY_SETS_PER_MUSCLE} this plan allows. Cut its volume.",
        )
        for muscle, sets in sorted(weekly.items())
        if sets > MAX_WEEKLY_SETS_PER_MUSCLE
    ]

    # Measured against what the template asked for rather than an absolute floor, and only
    # for muscles it undertook to train: a plan is not short of calf work it never set out
    # to do.
    if template is None:
        return issues

    issues += [
        _issue(
            f"{muscle.value} gets {_sets(weekly[muscle])} a week where the template "
            f"asks for {intended}.",
            severity=Severity.WARNING,
        )
        for muscle, intended in sorted(_template_weekly_sets(template).items())
        if weekly[muscle] < intended * WEEKLY_SETS_SHORTFALL
    ]

    return issues


def check_volume(context: PlanContext) -> list[VerificationIssue]:
    """Check the plan's schedule and training volume are within bounds."""

    slots = (
        {slot.slot_id: slot for slot in context.template.slots()}
        if context.template is not None
        else {}
    )

    issues = _check_schedule(context.plan, context.profile)
    for day in context.plan.training_days:
        for prescribed in day.exercises:
            slot = slots.get(prescribed.slot_id)
            issues += _check_reps(day, prescribed, slot)
            issues += _check_sets(day, prescribed, slot)
        issues += _check_day_volume(day)

    return issues + _check_weekly_volume(_weekly_sets(context), context.template)
