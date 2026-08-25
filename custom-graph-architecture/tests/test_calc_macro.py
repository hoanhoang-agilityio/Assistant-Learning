"""Tests for the ``calc_macro`` tool and the calorie and macro arithmetic behind it."""

import json

import pytest
from langchain.tools import ToolRuntime

from src.core.langgraph.tools import COACH_TOOLS, calc_macro
from src.core.langgraph.tools.calc_macro import NO_PROFILE
from src.schemas import (
    ActivityLevel,
    CoachContext,
    FitnessGoal,
    MacroTargets,
    NutritionTargets,
    Sex,
    TrainingPlan,
    UserProfile,
)
from src.services import nutrition
from tests.test_load_context import COMPLETE_PROFILE

# A 34-year-old man, 178 cm and 82.5 kg: Mifflin-St Jeor puts him at 1771.5 kcal at rest.
EXPECTED_BMR = 10 * 82.5 + 6.25 * 178.0 - 5 * 34 + 5


def _profile(**overrides) -> UserProfile:
    """A complete profile, with whatever this test needs to vary."""
    return UserProfile.model_validate(COMPLETE_PROFILE | overrides)


def _runtime(profile: dict | None) -> ToolRuntime:
    """The runtime the agent builds around a tool call, carrying the coach's context."""
    return ToolRuntime(
        state=None,
        config={},
        stream_writer=None,
        tool_call_id="call_1",
        store=None,
        context=CoachContext(profile=profile),
    )


# --- Basal metabolic rate ----------------------------------------------------------------


def test_the_published_equation_is_the_one_implemented() -> None:
    """A house variant of Mifflin-St Jeor would be unciteable and untestable."""
    assert nutrition.basal_metabolic_rate(_profile()) == EXPECTED_BMR


def test_sex_is_the_only_term_that_separates_two_identical_bodies() -> None:
    """The equation differs by its constant alone: 5 against -161, so 166 kcal apart."""
    male = nutrition.basal_metabolic_rate(_profile(sex=Sex.MALE))
    female = nutrition.basal_metabolic_rate(_profile(sex=Sex.FEMALE))

    assert male - female == 166


def test_a_heavier_user_burns_more_at_rest() -> None:
    """Body weight is the term the targets move with as the user's plan works."""
    assert nutrition.basal_metabolic_rate(
        _profile(current_weight_kg=92.5)
    ) > nutrition.basal_metabolic_rate(_profile(current_weight_kg=82.5))


# --- Maintenance -------------------------------------------------------------------------


@pytest.mark.parametrize("level", list(ActivityLevel))
def test_every_activity_level_the_profile_can_hold_has_a_factor(
    level: ActivityLevel,
) -> None:
    """A level with no multiplier raises inside a tool call and ends the agent's turn."""
    assert nutrition.maintenance_calories(1800, level) > 1800


def test_maintenance_rises_with_activity() -> None:
    """The multipliers have to stay ordered, or a desk job would out-eat a labourer."""
    by_level = [nutrition.maintenance_calories(1800, level) for level in ActivityLevel]

    assert by_level == sorted(by_level)


# --- The goal's adjustment ---------------------------------------------------------------


@pytest.mark.parametrize("goal", list(FitnessGoal))
def test_every_goal_the_profile_can_hold_is_priced(goal: FitnessGoal) -> None:
    """Each goal needs an adjustment and a protein target; a missing one raises."""
    targets = nutrition.calc_macros(_profile(goal=goal))

    assert targets.goal is goal
    assert targets.daily_calories > 0


def test_the_goal_sets_the_direction_off_maintenance() -> None:
    """Fat loss has to subtract and muscle gain has to add, or the plan contradicts itself."""
    profile = _profile()
    tdee = nutrition.calc_macros(profile, FitnessGoal.MAINTENANCE).tdee

    cut = nutrition.calc_macros(profile, FitnessGoal.FAT_LOSS).daily_calories
    gain = nutrition.calc_macros(profile, FitnessGoal.MUSCLE_GAIN).daily_calories
    hold = nutrition.calc_macros(profile, FitnessGoal.MAINTENANCE).daily_calories

    assert cut < hold <= tdee < gain


def test_the_profiles_own_goal_is_the_default() -> None:
    """The agent passes a goal only for a hypothetical; the plan's targets are the user's."""
    profile = _profile(goal=FitnessGoal.MUSCLE_GAIN)

    assert nutrition.calc_macros(profile) == nutrition.calc_macros(
        profile, FitnessGoal.MUSCLE_GAIN
    )


def test_a_percentage_deficit_is_still_held_above_the_floor() -> None:
    """20% off a small woman's maintenance is a number no one should be handed."""
    small = _profile(
        sex=Sex.FEMALE,
        age=30,
        height_cm=155.0,
        current_weight_kg=45.0,
        activity_level=ActivityLevel.SEDENTARY,
        goal=FitnessGoal.FAT_LOSS,
    )
    targets = nutrition.calc_macros(small)

    assert targets.daily_calories >= nutrition.CALORIE_FLOORS[Sex.FEMALE]
    assert targets.daily_calories < targets.tdee


# --- The macro split ---------------------------------------------------------------------


def test_protein_and_fat_are_set_from_body_weight() -> None:
    """Both are the terms with a floor to defend, so neither may float with calories."""
    macros = nutrition.split_macros(2400, 80.0, FitnessGoal.FAT_LOSS)

    assert macros.protein_g == round(
        nutrition.PROTEIN_G_PER_KG[FitnessGoal.FAT_LOSS] * 80
    )
    assert macros.fat_g == round(nutrition.FAT_G_PER_KG * 80)


def test_carbohydrate_absorbs_the_deficit() -> None:
    """It is the term with no minimum; cutting calories has to come out of it."""
    cut = nutrition.split_macros(2000, 80.0, FitnessGoal.FAT_LOSS)
    hold = nutrition.split_macros(2600, 80.0, FitnessGoal.FAT_LOSS)

    assert cut.protein_g == hold.protein_g
    assert cut.fat_g == hold.fat_g
    assert cut.carbs_g < hold.carbs_g


def test_an_impossible_target_zeroes_carbohydrate_rather_than_going_negative() -> None:
    """`MacroTargets` rejects a negative gram count, and a raising tool ends the turn."""
    macros = nutrition.split_macros(1000, 100.0, FitnessGoal.FAT_LOSS)

    assert macros.carbs_g == 0


@pytest.mark.parametrize("goal", list(FitnessGoal))
@pytest.mark.parametrize("weight_kg", [45.0, 82.5, 130.0])
def test_the_macros_come_to_the_calories_they_are_quoted_with(
    goal: FitnessGoal, weight_kg: float
) -> None:
    """The consistency check compares the two at 4/4/9; rounding may not split them."""
    targets = nutrition.calc_macros(_profile(goal=goal, current_weight_kg=weight_kg))

    assert targets.macros.calories == targets.daily_calories


# --- The tool ----------------------------------------------------------------------------


def test_the_tool_computes_from_the_profile_the_agent_was_invoked_with() -> None:
    """The body metrics are the input a hallucinated target would differ from."""
    result = calc_macro.invoke({"runtime": _runtime(COMPLETE_PROFILE)})

    assert result == nutrition.calc_macros(_profile()).model_dump(mode="json")


def test_the_tool_answers_a_hypothetical_goal_without_being_given_a_profile() -> None:
    """'What if I bulked instead?' is a QA question about a user who is cutting."""
    result = calc_macro.invoke(
        {"goal": FitnessGoal.MUSCLE_GAIN, "runtime": _runtime(COMPLETE_PROFILE)}
    )

    assert result["goal"] == FitnessGoal.MUSCLE_GAIN
    assert COMPLETE_PROFILE["goal"] == FitnessGoal.FAT_LOSS


def test_the_tool_returns_json_the_agent_can_read() -> None:
    """Enums left as objects reach the model as `FitnessGoal.FAT_LOSS`."""
    result = calc_macro.invoke({"runtime": _runtime(COMPLETE_PROFILE)})

    assert json.dumps(result)


def test_the_tool_returns_the_fields_a_plan_copies() -> None:
    """`daily_calories` and `macros` go straight onto the plan the gate checks."""
    result = calc_macro.invoke({"runtime": _runtime(COMPLETE_PROFILE)})
    targets = NutritionTargets.model_validate(result)

    plan = TrainingPlan.model_validate(
        {
            "template_id": "upper_lower_4day",
            "goal": targets.goal,
            "daily_calories": targets.daily_calories,
            "macros": targets.macros.model_dump(),
            "training_days": [
                {
                    "day_number": 1,
                    "name": "Upper",
                    "exercises": [
                        {
                            "slot_id": "s1",
                            "exercise_id": "bench_press",
                            "sets": 3,
                            "reps": "8-12",
                        }
                    ],
                }
            ],
        }
    )

    assert plan.macros.calories == plan.daily_calories


def test_no_profile_is_said_in_words() -> None:
    """A raising tool ends the turn; the agent has to be told to ask for the metrics."""
    assert calc_macro.invoke({"runtime": _runtime(None)}) == {"error": NO_PROFILE}


def test_an_incomplete_profile_is_refused_rather_than_guessed_around() -> None:
    """Half a profile computes a number that looks authoritative and is not."""
    result = calc_macro.invoke({"runtime": _runtime({"age": 34, "sex": "MALE"})})

    assert result == {"error": NO_PROFILE}


# --- Binding -----------------------------------------------------------------------------


def test_the_coach_is_handed_the_targets_rather_than_this_tool() -> None:
    """A pure function of the profile is a round trip the plan does not have to pay for."""
    assert calc_macro not in COACH_TOOLS


def test_the_model_may_choose_the_goal_and_nothing_else() -> None:
    """Body metrics passed as arguments are metrics the model could invent."""
    assert set(calc_macro.args) == {"goal"}


def test_the_macro_targets_the_tool_reports_are_the_plans_own_model() -> None:
    """The gate reads `MacroTargets`; a parallel shape would drift away from it."""
    assert isinstance(nutrition.calc_macros(_profile()).macros, MacroTargets)
