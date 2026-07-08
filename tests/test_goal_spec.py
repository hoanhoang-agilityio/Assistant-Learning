"""Tests for GoalSpec derivation and feasibility."""

from core.profile.goal_spec import (
    assess_goal_feasibility,
    derive_goal_spec_fields,
    rate_to_calorie_adjustment,
)


def test_derive_goal_spec_fields_from_delta_and_horizon() -> None:
    profile = {
        "goal": "muscle_gain",
        "current_weight_kg": 73.0,
        "weight_delta_kg": 2.0,
        "horizon_weeks": 52,
    }
    derived = derive_goal_spec_fields(profile)
    assert derived["target_weight_kg"] == 75.0
    assert derived["weekly_rate_kg"] == round(2 / 52, 3)
    assert derived["goal_archetype"] == "muscle_gain_lean_bulk"


def test_unsafe_fat_loss_timeline_requires_hitl() -> None:
    profile = {
        "goal": "fat_loss",
        "current_weight_kg": 90.0,
        "weight_delta_kg": -5.0,
        "horizon_weeks": 4,
    }
    derived = derive_goal_spec_fields(profile)
    feasibility = assess_goal_feasibility({**profile, **derived})
    assert feasibility["level"] == "unsafe"
    assert feasibility["requires_hitl"] is True


def test_rate_to_calorie_adjustment_uses_weekly_rate() -> None:
    calories = rate_to_calorie_adjustment("muscle_gain", 2500, 0.04)
    assert calories > 2500
    assert calories < 2700
