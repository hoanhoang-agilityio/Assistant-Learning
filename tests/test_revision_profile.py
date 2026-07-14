from core.profile.extraction import configure_profile_extractor
from core.profile.schema import Constraints, ExtractedProfile
from core.subgraphs.fitness.schema import StructuredWorkout, WorkoutDay, WorkoutExercise
from core.subgraphs.fitness.utils import (
    ensure_training_day_count,
)
from core.subgraphs.user.utils import apply_revision_overrides, extract_profile


def test_apply_revision_overrides_updates_days_per_week() -> None:
    configure_profile_extractor(
        lambda _query: ExtractedProfile(constraints=Constraints(days_per_week=5))
    )
    profile = {
        "age": 27,
        "sex": "male",
        "height_cm": 171,
        "current_weight_kg": 73.0,
        "target_weight_kg": 70.0,
        "goal": "fat_loss",
        "days_per_week": 4,
        "activity_level": "gym_4x_week",
        "equipment": "gym",
    }
    updated = apply_revision_overrides(profile, "i want to change to train 5 days per week")
    assert updated["days_per_week"] == 5
    assert updated["activity_level"] == "gym_5x_week"
    assert updated["age"] == 27
    assert updated["goal"] == "fat_loss"


def test_extract_profile_applies_revision_without_reasking_profile(complete_profile: dict) -> None:
    """Relocated from planning: revision-feedback re-extraction is now owned by the User
    subgraph (core.subgraphs.user.utils.extract_profile). End-to-end pause/resume/REPLAN
    coverage for this behavior lives in tests/test_user_subgraph.py.
    """
    configure_profile_extractor(
        lambda query: (
            ExtractedProfile(constraints=Constraints(days_per_week=5))
            if "5 days" in query.lower()
            else ExtractedProfile()
        )
    )
    profile = extract_profile(
        query="I want a 4-day training plan to lose weight.",
        user_profile=complete_profile,
        constraints={"days_per_week": 4, "equipment": "gym"},
        revision_feedback="i want to change to train 5 days per week",
    )
    assert profile["days_per_week"] == 5
    assert profile["activity_level"] == "gym_5x_week"


def test_apply_revision_overrides_parses_days_from_natural_language() -> None:
    profile = {
        "age": 27,
        "sex": "male",
        "height_cm": 171,
        "current_weight_kg": 73.0,
        "target_weight_kg": 70.0,
        "goal": "fat_loss",
        "days_per_week": 4,
        "activity_level": "gym_4x_week",
        "equipment": "gym",
    }
    configure_profile_extractor(lambda _query: ExtractedProfile())
    updated = apply_revision_overrides(profile, "i want to train 3 days per week")
    assert updated["days_per_week"] == 3
    assert updated["activity_level"] == "gym_3x_week"


def test_ensure_training_day_count_fills_missing_days() -> None:
    workout = StructuredWorkout(
        split="full body",
        goal="fat_loss",
        days=[
            WorkoutDay(
                name="Day 1",
                focus="full body",
                exercises=[WorkoutExercise(name="Squat", sets=3, reps="8-10")],
            )
        ],
        weekly_sets=3,
        progression="Add load weekly.",
        substitutions=[],
        notes=[],
        evidence_applied=[],
    )
    repaired = ensure_training_day_count(
        workout,
        {"days_per_week": 3, "equipment": "gym"},
        {"goal": "fat_loss", "days_per_week": 3},
    )
    assert len(repaired.days) == 3
