"""Schema completeness.

Pydantic already guarantees the plan's shape; this checks it is complete against its own
template. Every slot the template requires is filled exactly once and on the day that owns
it, the plan's days are the template's days, and every ``exercise_id`` resolves to a
catalogue row — the check that stops an invented movement reaching the user.

The rule reads the template through ``template_id``, which is the only thing tying a plan
back to what it was meant to build. A plan naming a template that does not exist is
reported and its slots left unchecked: there is nothing to check them against.
"""

from collections import Counter

from src.schemas import (
    CheckName,
    TrainingPlan,
    VerificationIssue,
    WorkoutTemplate,
)
from src.verification.deterministic.context import PlanContext


def _issue(message: str, **location: object) -> VerificationIssue:
    """One completeness issue, located in the plan. Every one of these fails the gate."""

    return VerificationIssue(check=CheckName.COMPLETENESS, message=message, **location)


def _check_days(
    plan: TrainingPlan, template: WorkoutTemplate
) -> list[VerificationIssue]:
    """Check the plan's training days are the template's, once each."""

    planned = [day.day_number for day in plan.training_days]
    required = [day.day_number for day in template.training_days]

    issues = [
        _issue(
            f"The plan has no day {day_number}. Template '{template.id}' trains days "
            f"{sorted(required)}; add the missing day.",
            day_number=day_number,
            field="training_days",
        )
        for day_number in sorted(set(required) - set(planned))
    ]
    issues += [
        _issue(
            f"Day {day_number} is not in template '{template.id}', which trains days "
            f"{sorted(required)}. Remove it or renumber it.",
            day_number=day_number,
            field="training_days",
        )
        for day_number in sorted(set(planned) - set(required))
    ]
    issues += [
        _issue(
            f"Day {day_number} appears {count} times. Number each training day once.",
            day_number=day_number,
            field="training_days",
        )
        for day_number, count in sorted(Counter(planned).items())
        if count > 1
    ]

    return issues


def _check_slots(
    plan: TrainingPlan, template: WorkoutTemplate
) -> list[VerificationIssue]:
    """Check every slot the template requires is filled exactly once, on the right day.

    A slot belonging to another day is reported as the misplacement it is rather than as
    an unknown id: the exercise may well be right, on the wrong day.
    """

    template_days = {day.day_number: day for day in template.training_days}
    slot_owner = {
        slot.slot_id: day.day_number
        for day in template.training_days
        for slot in day.exercise_slots
    }

    issues = []
    for day in plan.training_days:
        template_day = template_days.get(day.day_number)
        # A day the template does not have is _check_days' finding; reporting each of its
        # slots as unknown as well would bury it.
        if template_day is None:
            continue

        required = {slot.slot_id for slot in template_day.exercise_slots}
        filled = {prescribed.slot_id for prescribed in day.exercises}
        issues += [
            _issue(
                f"Day {day.day_number} leaves slot '{slot_id}' unfilled. Every slot the "
                f"template requires needs an exercise.",
                day_number=day.day_number,
                slot_id=slot_id,
            )
            for slot_id in sorted(required - filled)
        ]

        for prescribed in day.exercises:
            if prescribed.slot_id in required:
                continue

            owner = slot_owner.get(prescribed.slot_id)
            message = (
                f"Slot '{prescribed.slot_id}' belongs to day {owner}, not day "
                f"{day.day_number}. Move the prescription to the day that owns it."
                if owner is not None
                else f"Template '{template.id}' has no slot '{prescribed.slot_id}'. "
                f"Fill the slots the template lists and invent none."
            )
            issues.append(
                _issue(
                    message,
                    day_number=day.day_number,
                    slot_id=prescribed.slot_id,
                    exercise_id=prescribed.exercise_id,
                )
            )

    issues += [
        _issue(
            f"Slot '{slot_id}' is filled {count} times. Each slot takes one exercise.",
            slot_id=slot_id,
        )
        for slot_id, count in sorted(Counter(plan.filled_slot_ids()).items())
        if count > 1
    ]

    return issues


def _check_exercises(context: PlanContext) -> list[VerificationIssue]:
    """Check every prescription names an exercise the catalogue actually holds."""

    return [
        _issue(
            f"'{prescribed.exercise_id}' is not an exercise in the catalogue. Fill slot "
            f"'{prescribed.slot_id}' with an id returned by load_exercise.",
            day_number=day.day_number,
            slot_id=prescribed.slot_id,
            exercise_id=prescribed.exercise_id,
        )
        for day in context.plan.training_days
        for prescribed in day.exercises
        if context.exercise_for(prescribed.exercise_id) is None
    ]


def check_completeness(context: PlanContext) -> list[VerificationIssue]:
    """Check the plan fills its template exactly, with real exercises."""

    plan = context.plan
    if context.template is None:
        return [
            _issue(
                f"Template '{plan.template_id}' is not in the catalogue. Rebuild the "
                f"plan from a template returned by load_template.",
                field="template_id",
            ),
            # Still worth running: an invented exercise id does not need the template.
            *_check_exercises(context),
        ]

    return [
        *_check_days(plan, context.template),
        *_check_slots(plan, context.template),
        *_check_exercises(context),
    ]
