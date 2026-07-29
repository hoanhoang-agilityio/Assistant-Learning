"""Tests for deterministic workout safety markup / equipment gates."""

from core.subgraphs.fitness.utils import (
    collect_unsafe_markup_feedback,
    contains_unsafe_markup,
    validate_workout_safety_data,
)


def _minimal_workout(*, exercise_name: str = "Squat", notes: str | None = None) -> dict:
    return {
        "split": "3-day",
        "goal": "fat_loss",
        "weekly_sets": 3,
        "days": [
            {
                "name": "Day 1",
                "focus": "Full",
                "exercises": [
                    {
                        "name": exercise_name,
                        "sets": 3,
                        "reps": "8-12",
                        "notes": notes,
                    }
                ],
            }
        ],
        "notes": [],
        "substitutions": [],
        "evidence_applied": [],
    }


def test_contains_unsafe_markup_detects_script() -> None:
    assert contains_unsafe_markup("tempo; <script>alert(1)</script>")
    assert not contains_unsafe_markup("Controlled tempo; stop 2 reps shy.")


def test_validate_workout_safety_rejects_xss_notes() -> None:
    workout = _minimal_workout(notes="add <script>alert('xss')</script>")
    result = validate_workout_safety_data(
        profile={"age": 30, "current_weight_kg": 80, "height_cm": 175, "sex": "male"},
        macro_targets=None,
        training_constraints={"days_per_week": 3, "equipment": "bodyweight"},
        structured_workout=workout,
    )
    assert result["passed"] is False
    assert any(code.startswith("unsafe_markup_in_notes:") for code in result["feedback"])


def test_validate_workout_safety_rejects_gym_machine_on_bodyweight() -> None:
    workout = _minimal_workout(exercise_name="Leg Press")
    result = validate_workout_safety_data(
        profile={"age": 30, "current_weight_kg": 80, "height_cm": 175, "sex": "male"},
        macro_targets=None,
        training_constraints={"days_per_week": 3, "equipment": "bodyweight"},
        structured_workout=workout,
    )
    assert result["passed"] is False
    assert any(code.startswith("equipment_mismatch:bodyweight:") for code in result["feedback"])


def test_collect_unsafe_markup_feedback_plan_notes() -> None:
    from core.subgraphs.fitness.schema import StructuredWorkout

    workout = StructuredWorkout.model_validate(
        {
            **_minimal_workout(),
            "notes": ["Welcome <script>x</script>"],
        }
    )
    feedback = collect_unsafe_markup_feedback(workout)
    assert "unsafe_markup_in_plan_notes" in feedback
