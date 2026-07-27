"""Tests for GoalSpec derivation and feasibility."""

from core.profile.goal_spec import (
    assess_goal_feasibility,
    derive_goal_spec,
    rate_to_calorie_adjustment,
)
from core.subgraphs.user.utils import merge_form_submission


def test_derive_goal_spec_from_target_and_horizon() -> None:
    profile = {
        "goal": "muscle_gain",
        "current_weight_kg": 73.0,
        "target_weight_kg": 75.0,
        "horizon_weeks": 52,
    }
    goal_spec = derive_goal_spec(profile)
    assert goal_spec.weight_delta_kg == 2.0
    assert goal_spec.weekly_rate_kg == round(2 / 52, 3)
    assert goal_spec.goal_archetype == "muscle_gain_lean_bulk"
    assert goal_spec.goal_direction == "gain"


def test_unsafe_fat_loss_timeline_requires_hitl() -> None:
    profile = {
        "goal": "fat_loss",
        "current_weight_kg": 90.0,
        "target_weight_kg": 85.0,
        "horizon_weeks": 4,
    }
    goal_spec = derive_goal_spec(profile)
    feasibility = assess_goal_feasibility(
        goal=goal_spec.goal,
        weight_delta_kg=goal_spec.weight_delta_kg,
        weekly_rate_kg=goal_spec.weekly_rate_kg,
    )
    assert feasibility["level"] == "unsafe"
    assert goal_spec.requires_hitl is True


def test_rate_to_calorie_adjustment_uses_weekly_rate() -> None:
    calories = rate_to_calorie_adjustment("muscle_gain", 2500, 0.04)
    assert calories > 2500
    assert calories < 2700


def test_goal_spec_is_immutable() -> None:
    goal_spec = derive_goal_spec({"goal": "fat_loss", "current_weight_kg": 90.0})
    try:
        goal_spec.goal_archetype = "muscle_gain_lean_bulk"
        raised = False
    except Exception:
        raised = True
    assert raised, "GoalSpec must be frozen -- mutation should raise"


def test_stale_weight_delta_does_not_survive_a_corrected_resubmission() -> None:
    """Regression test for the original bug: submitting an invalid target_weight_kg
    (fat-loss goal, target above current) then correcting it on a second submission must
    not leave a stale `weight_delta_kg` behind that re-triggers the same validation error.
    """
    profile = {"age": 30, "sex": "male", "height_cm": 175.0, "goal": "fat_loss"}

    first_submission = {"current_weight_kg": 70, "target_weight_kg": 75}
    profile = merge_form_submission(profile, first_submission)
    first_goal_spec = derive_goal_spec(profile)
    assert "goal_direction_conflict:fat_loss_positive_delta" in first_goal_spec.feasibility_issues

    second_submission = {"current_weight_kg": 70, "target_weight_kg": 68}
    profile = merge_form_submission(profile, second_submission)

    # profile is raw-inputs-only: no derived field can go stale because none is ever stored.
    assert "weight_delta_kg" not in profile
    assert "weekly_rate_kg" not in profile
    assert "feasibility_level" not in profile
    assert "goal_archetype" not in profile

    second_goal_spec = derive_goal_spec(profile)
    assert second_goal_spec.weight_delta_kg == -2.0
    assert second_goal_spec.goal_direction == "loss"
    assert second_goal_spec.feasibility_issues == []
    assert second_goal_spec.requires_hitl is False
