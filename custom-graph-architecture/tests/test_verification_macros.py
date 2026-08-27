"""Tests for the macro rule: the arithmetic the coach agent is not trusted to do."""

import pytest

from src.core.langgraph.verification.deterministic.context import PlanContext
from src.core.langgraph.verification.deterministic.macros import check_macros
from src.enums import (
    ActivityLevel,
    FitnessGoal,
    Sex,
)
from src.schemas import (
    CheckName,
    MacroTargets,
    PlanDay,
    PlannedExercise,
    Severity,
    TrainingPlan,
    UserProfile,
)
from src.services.nutrition import calc_macros

MALE = UserProfile(
    age=34,
    sex=Sex.MALE,
    height_cm=178.0,
    current_weight_kg=82.5,
    activity_level=ActivityLevel.MODERATE,
    goal=FitnessGoal.FAT_LOSS,
    training_days_per_week=2,
)

FEMALE = UserProfile(
    age=29,
    sex=Sex.FEMALE,
    height_cm=164.0,
    current_weight_kg=58.0,
    activity_level=ActivityLevel.LIGHT,
    goal=FitnessGoal.FAT_LOSS,
    training_days_per_week=3,
)


def plan_with(
    daily_calories: int,
    macros: MacroTargets,
    goal: FitnessGoal = FitnessGoal.FAT_LOSS,
) -> TrainingPlan:
    """A plan carrying the given targets. The training week is beside the point here."""
    return TrainingPlan(
        template_id="tpl-upper-lower",
        goal=goal,
        daily_calories=daily_calories,
        macros=macros,
        training_days=[
            PlanDay(
                day_number=1,
                name="Upper",
                exercises=[
                    PlannedExercise(
                        slot_id="d1-s1",
                        exercise_id="ex-bench-press",
                        sets=3,
                        reps="8-12",
                    )
                ],
            )
        ],
    )


def correct_plan(profile: UserProfile = MALE) -> TrainingPlan:
    """The plan the coach would produce if it used calc_macro and copied the answer."""
    targets = calc_macros(profile)
    return plan_with(targets.daily_calories, targets.macros, goal=profile.goal)


def context_for(plan: TrainingPlan, profile: UserProfile = MALE) -> PlanContext:
    """A resolved context. This rule reads no template and no catalogue."""
    return PlanContext(plan=plan, profile=profile, template=None, exercises={})


def fields(plan: TrainingPlan, profile: UserProfile = MALE) -> set[str | None]:
    """The plan fields the rule objected to."""
    return {issue.field for issue in check_macros(context_for(plan, profile))}


# --- The plan that is right -------------------------------------------------------------


@pytest.mark.parametrize("profile", [MALE, FEMALE])
def test_the_targets_calc_macro_returns_are_accepted(profile: UserProfile) -> None:
    """The tool's own output must pass, or the coach can never satisfy the gate."""
    assert check_macros(context_for(correct_plan(profile), profile)) == []


# --- Macros against their own calorie target --------------------------------------------


def test_macros_that_do_not_add_up_fail_the_gate() -> None:
    """4/4/9 is not negotiable: a stated target the macros contradict is one of them wrong."""
    plan = plan_with(2198, MacroTargets(protein_g=182, carbs_g=350, fat_g=66))

    [issue] = check_macros(context_for(plan))

    assert issue.check is CheckName.MACROS
    assert issue.severity is Severity.ERROR
    assert issue.field == "macros"


def test_whole_gram_rounding_is_not_a_failure() -> None:
    """calc_macro rounds grams, so an exact sum is not something any plan can hold to."""
    targets = calc_macros(MALE)
    rounded = MacroTargets(
        protein_g=targets.macros.protein_g,
        carbs_g=targets.macros.carbs_g - 1,
        fat_g=targets.macros.fat_g,
    )

    assert check_macros(context_for(plan_with(targets.daily_calories, rounded))) == []


# --- Calories against the profile -------------------------------------------------------


def test_a_target_the_profile_does_not_support_fails_the_gate() -> None:
    """The case that matters: a deficit the agent invented rather than computed."""
    plan = plan_with(1700, MacroTargets(protein_g=182, carbs_g=94, fat_g=66))

    assert "daily_calories" in fields(plan)


def test_a_target_rounded_for_the_user_is_accepted() -> None:
    """2200 instead of 2198 is a coach being readable, not a coach being wrong."""
    plan = plan_with(2200, MacroTargets(protein_g=182, carbs_g=219, fat_g=66))

    assert check_macros(context_for(plan)) == []


def test_the_message_gives_the_number_the_profile_implies() -> None:
    """A revision prompt saying only 'wrong' costs a retry to say what this says now."""
    plan = plan_with(1700, MacroTargets(protein_g=182, carbs_g=94, fat_g=66))

    [issue] = check_macros(context_for(plan))

    assert "2198" in issue.message


# --- The calorie floor ------------------------------------------------------------------


def test_a_target_below_the_floor_fails_the_gate() -> None:
    """Percentage adjustments off maintenance can land somewhere nobody should eat."""
    plan = plan_with(1300, MacroTargets(protein_g=140, carbs_g=45, fat_g=62))

    assert any(
        "floor" in issue.message for issue in check_macros(context_for(plan, MALE))
    )


def test_the_floor_is_the_one_for_this_user() -> None:
    """1300 kcal is under the floor for a man and over it for a woman."""
    plan = plan_with(1300, MacroTargets(protein_g=140, carbs_g=45, fat_g=62))

    assert not any(
        "floor" in issue.message for issue in check_macros(context_for(plan, FEMALE))
    )


# --- The goal ---------------------------------------------------------------------------


def test_a_plan_built_for_another_goal_fails_the_gate() -> None:
    """Goal drives the calorie adjustment and the protein target; wrong goal, wrong plan."""
    plan = plan_with(
        2198,
        MacroTargets(protein_g=182, carbs_g=219, fat_g=66),
        goal=FitnessGoal.MUSCLE_GAIN,
    )

    assert fields(plan) == {"goal"}


def test_the_wrong_goal_does_not_drag_its_calories_in_with_it() -> None:
    """One mistake, one finding: the targets are only wrong because the goal is."""
    plan = plan_with(
        3000,
        MacroTargets(protein_g=200, carbs_g=400, fat_g=67),
        goal=FitnessGoal.MUSCLE_GAIN,
    )

    assert fields(plan) == {"goal"}


def test_the_wrong_goal_does_not_hide_macros_that_do_not_add_up() -> None:
    """That sum is wrong whatever goal it was meant to serve."""
    plan = plan_with(
        2198,
        MacroTargets(protein_g=182, carbs_g=350, fat_g=66),
        goal=FitnessGoal.MUSCLE_GAIN,
    )

    assert fields(plan) == {"goal", "macros"}


# --- Protein --------------------------------------------------------------------------


def test_a_protein_shortfall_is_a_warning_rather_than_a_failure() -> None:
    """Worth telling the coach; not worth spending a retry and stranding the user."""
    plan = plan_with(2198, MacroTargets(protein_g=100, carbs_g=301, fat_g=66))

    [issue] = check_macros(context_for(plan))

    assert issue.severity is Severity.WARNING
    assert issue.field == "macros.protein_g"


def test_protein_a_little_under_target_is_left_alone() -> None:
    """The target is a recommendation, not a figure the split has to hit exactly."""
    plan = plan_with(2198, MacroTargets(protein_g=170, carbs_g=222, fat_g=66))

    assert check_macros(context_for(plan)) == []


def test_protein_over_target_is_never_a_finding() -> None:
    """More protein than the goal asks for is a choice, not an error."""
    plan = plan_with(2198, MacroTargets(protein_g=220, carbs_g=181, fat_g=66))

    assert check_macros(context_for(plan)) == []
