"""Exercise availability and user constraints.

Whether this user can actually perform this plan, and whether each prescription does the
job the slot was written for. The coach picks from ``load_exercise``, which already filters
by equipment and ranks by target muscle — this rule is what notices when it prescribed
something the tool never handed it.

A prescription is worth at most two findings: whether the user can equip it, and whether
it fits its slot. The two are independent — an exercise can fit the slot perfectly and
still be one the user does not own — but the several ways an exercise can miss a slot are
one mistake and one swap, so they are reported as one.

Slot fit needs the template, so those checks are skipped when it does not resolve or when
the prescription names a slot the template has no record of; both are task 5.1's finding.
Equipment needs neither, and is checked either way.
"""

from src.core.langgraph.verification.deterministic.context import PlanContext
from src.enums import (
    EquipmentType,
    MuscleGroup,
)
from src.schemas import (
    CheckName,
    Exercise,
    ExerciseSlot,
    PlanDay,
    PlannedExercise,
    Severity,
    UserProfile,
    VerificationIssue,
)
from src.services.catalogue import equipment_available

_FROM_THE_TOOL = "Fill the slot from load_exercise, which only returns what fits it."


def _issue(
    message: str,
    day: PlanDay,
    prescribed: PlannedExercise,
    severity: Severity = Severity.ERROR,
) -> VerificationIssue:
    """One availability issue, located at the prescription that caused it."""

    return VerificationIssue(
        check=CheckName.AVAILABILITY,
        message=message,
        severity=severity,
        day_number=day.day_number,
        slot_id=prescribed.slot_id,
        exercise_id=prescribed.exercise_id,
    )


def _names(values: list[MuscleGroup] | set[EquipmentType]) -> str:
    """An enum collection as a readable list, ordered so a message never varies."""

    return ", ".join(sorted(value.value for value in values))


def _check_equipment(exercise: Exercise, profile: UserProfile) -> str | None:
    """Whether the user owns what the exercise needs, and what is missing if not."""

    if equipment_available(exercise, profile.available_equipment):
        return None

    missing = (
        set(exercise.equipment)
        - {EquipmentType.BODYWEIGHT}
        - set(profile.available_equipment.equipment)
    )
    return (
        f"{exercise.name} needs {_names(missing)}, which the user does not have. "
        f"{_FROM_THE_TOOL}"
    )


def _check_pattern(
    exercise: Exercise, slot: ExerciseSlot
) -> tuple[Severity, str] | None:
    """Whether the exercise's movement pattern is one the slot accepts."""

    if slot.accepts_pattern(exercise.movement_pattern):
        return None

    return Severity.ERROR, (
        f"{exercise.name} is a {exercise.movement_pattern.value} movement, which slot "
        f"'{slot.slot_id}' does not take. {_FROM_THE_TOOL}"
    )


def _check_region(
    exercise: Exercise, slot: ExerciseSlot
) -> tuple[Severity, str] | None:
    """Whether the exercise trains the body region the slot requires."""

    required = slot.required_body_region
    if required is None or exercise.body_region is required:
        return None

    return Severity.ERROR, (
        f"{exercise.name} is a {exercise.body_region.value} exercise but slot "
        f"'{slot.slot_id}' requires {required.value}. {_FROM_THE_TOOL}"
    )


def _check_muscles(
    exercise: Exercise, slot: ExerciseSlot
) -> tuple[Severity, str] | None:
    """Whether the exercise trains what the slot is for, and how centrally.

    A slot naming several muscles is asking for one exercise that covers them, not for all
    of them at once, so one primary hit is enough. Training them only as secondaries is
    worth saying — the day still gets the work, further down the exercise than intended.
    """

    wanted = set(slot.target_muscles)
    if not wanted:
        return None

    if wanted & set(exercise.primary_muscles):
        return None

    if wanted & set(exercise.secondary_muscles):
        return Severity.WARNING, (
            f"{exercise.name} trains {_names(slot.target_muscles)} only as a secondary "
            f"muscle, and slot '{slot.slot_id}' is written for it. Prefer an exercise "
            f"that trains it directly."
        )

    return Severity.ERROR, (
        f"{exercise.name} does not train {_names(slot.target_muscles)}, which slot "
        f"'{slot.slot_id}' is for — it trains {_names(exercise.primary_muscles)}. "
        f"{_FROM_THE_TOOL}"
    )


def _slot_fit(exercise: Exercise, slot: ExerciseSlot) -> tuple[Severity, str] | None:
    """The one thing to say about an exercise that does not fit its slot.

    An exercise chosen for the wrong slot is usually wrong in several ways at once — a
    squat in a chest slot trains the wrong muscle, in the wrong pattern, in the wrong
    region — and all three are the same swap. The muscle is reported ahead of the movement
    because it says plainest what the slot wanted. A warning never stands in for an error.
    """

    findings = [
        finding
        for check in (_check_muscles, _check_pattern, _check_region)
        if (finding := check(exercise, slot)) is not None
    ]
    errors = [finding for finding in findings if finding[0] is Severity.ERROR]

    return next(iter(errors or findings), None)


def _check_prescription(
    context: PlanContext,
    day: PlanDay,
    prescribed: PlannedExercise,
    slots: dict[str, ExerciseSlot],
) -> list[VerificationIssue]:
    """Every availability and fit finding against one prescription."""

    exercise = context.exercise_for(prescribed.exercise_id)
    if exercise is None:
        return []

    issues = []
    equipment = _check_equipment(exercise, context.profile)
    if equipment is not None:
        issues.append(_issue(equipment, day, prescribed))

    slot = slots.get(prescribed.slot_id)
    if slot is None:
        return issues

    fit = _slot_fit(exercise, slot)
    if fit is not None:
        severity, message = fit
        issues.append(_issue(message, day, prescribed, severity=severity))

    return issues


def check_availability(context: PlanContext) -> list[VerificationIssue]:
    """Check every prescription is available to the user and fits the slot it fills."""

    slots = (
        {slot.slot_id: slot for slot in context.template.slots()}
        if context.template is not None
        else {}
    )

    return [
        issue
        for day in context.plan.training_days
        for prescribed in day.exercises
        for issue in _check_prescription(context, day, prescribed, slots)
    ]
