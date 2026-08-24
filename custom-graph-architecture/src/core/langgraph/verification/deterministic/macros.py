"""Macro consistency.

Arithmetic the agent is not trusted to do. The coach has ``calc_macro`` and is told to use
it; this rule is what notices when it did the sum in its head instead. Four things have to
hold: the macros add up to the calorie target the plan states, that target is the one the
profile implies, it sits above the floor below which a number stops being a target, and
the goal the macros were computed for is the user's own.

Everything downstream of the goal is skipped when the goal itself is wrong — recomputing
against a goal the user does not have would report the same mistake three more times.

The tolerances are relative rather than absolute so they mean the same thing to a 1400 kcal
user and a 3200 kcal one.
"""

from src.core.langgraph.verification.deterministic.context import PlanContext
from src.schemas import (
    CheckName,
    NutritionTargets,
    Severity,
    TrainingPlan,
    UserProfile,
    VerificationIssue,
)
from src.services.nutrition import CALORIE_FLOORS, calc_macros

# Whole-gram rounding moves the sum by under 10 kcal, so anything past this is the agent
# having added up wrong rather than having rounded.
MACRO_SUM_TOLERANCE = 0.02

# Room for the coach to round a target to something a user can hold in their head, and no
# room to invent a deficit the profile does not support.
CALORIE_TARGET_TOLERANCE = 0.05

# Protein is the macro a goal actually depends on, and the one a calorie-first split tends
# to squeeze. Under target by more than this is worth saying, not worth failing a plan for.
PROTEIN_SHORTFALL_TOLERANCE = 0.20

_RECOMPUTE = "Recompute the targets with calc_macro and use what it returns."


def _issue(
    message: str, severity: Severity = Severity.ERROR, **location: object
) -> VerificationIssue:
    """One macro issue. These are about the plan as a whole, not about any one day."""

    return VerificationIssue(
        check=CheckName.MACROS, message=message, severity=severity, **location
    )


def _relative_gap(actual: float, expected: float) -> float:
    """How far off a number is, as a fraction of what it should have been."""

    return abs(actual - expected) / expected


def _check_goal(plan: TrainingPlan, profile: UserProfile) -> list[VerificationIssue]:
    """Check the plan was built for the goal the user actually has."""

    if plan.goal is profile.goal:
        return []

    return [
        _issue(
            f"The plan is built for {plan.goal.value} but the user's goal is "
            f"{profile.goal.value}. Rebuild it for their goal.",
            field="goal",
        )
    ]


def _check_macro_sum(plan: TrainingPlan) -> list[VerificationIssue]:
    """Check the macros add up to the calorie target stated beside them."""

    summed = plan.macros.calories
    if _relative_gap(summed, plan.daily_calories) <= MACRO_SUM_TOLERANCE:
        return []

    return [
        _issue(
            f"The macros come to {summed:.0f} kcal but the plan states "
            f"{plan.daily_calories} kcal. {_RECOMPUTE}",
            field="macros",
        )
    ]


def _check_calorie_target(
    plan: TrainingPlan, targets: NutritionTargets
) -> list[VerificationIssue]:
    """Check the calorie target is the one the user's profile and goal imply."""

    if _relative_gap(plan.daily_calories, targets.daily_calories) <= (
        CALORIE_TARGET_TOLERANCE
    ):
        return []

    return [
        _issue(
            f"The plan states {plan.daily_calories} kcal a day, but the user's profile "
            f"and goal give {targets.daily_calories} kcal "
            f"(maintenance {targets.tdee}). {_RECOMPUTE}",
            field="daily_calories",
        )
    ]


def _check_calorie_floor(
    plan: TrainingPlan, profile: UserProfile
) -> list[VerificationIssue]:
    """Check the target has not been cut below what anyone should be handed."""

    floor = CALORIE_FLOORS[profile.sex]
    if plan.daily_calories >= floor:
        return []

    return [
        _issue(
            f"{plan.daily_calories} kcal a day is below the {floor} kcal floor for this "
            f"user. Raise the target to at least the floor.",
            field="daily_calories",
        )
    ]


def _check_protein(
    plan: TrainingPlan, targets: NutritionTargets
) -> list[VerificationIssue]:
    """Check the split left enough protein for the goal it serves."""

    target_g = targets.macros.protein_g
    shortfall = (target_g - plan.macros.protein_g) / target_g
    if shortfall <= PROTEIN_SHORTFALL_TOLERANCE:
        return []

    return [
        _issue(
            f"Protein is {plan.macros.protein_g:.0f}g against a target of "
            f"{target_g:.0f}g for {targets.goal.value}. Raise it and take the calories "
            f"from carbs or fat.",
            severity=Severity.WARNING,
            field="macros.protein_g",
        )
    ]


def check_macros(context: PlanContext) -> list[VerificationIssue]:
    """Check the plan's calories and macros agree with each other and with the profile."""

    plan, profile = context.plan, context.profile

    # These two hold whatever goal the plan was built for: one is internal arithmetic, the
    # other is a floor on the number itself.
    issues = [*_check_macro_sum(plan), *_check_calorie_floor(plan, profile)]

    goal_issues = _check_goal(plan, profile)
    if goal_issues:
        return [*goal_issues, *issues]

    targets = calc_macros(profile)
    return [
        *issues,
        *_check_calorie_target(plan, targets),
        *_check_protein(plan, targets),
    ]
