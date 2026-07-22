from core.profile.extraction import configure_profile_extractor
from core.profile.schema import Constraints, ExtractedProfile
from core.subgraphs.fitness.schema import (
    EditOperation,
    StructuredWorkout,
    WorkoutDay,
    WorkoutExercise,
)
from core.subgraphs.fitness.utils import (
    ensure_training_day_count,
    resolve_expected_day_count,
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
    assert updated["_days_per_week_explicit"] is True


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
        profile={**complete_profile, "days_per_week": 4, "equipment": "gym"},
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
    assert updated["_days_per_week_explicit"] is True


def test_apply_revision_overrides_no_explicit_flag_when_days_not_mentioned() -> None:
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
    updated = apply_revision_overrides(profile, "replace bench press with dumbbell press")
    assert updated["days_per_week"] == 4
    assert updated["_days_per_week_explicit"] is False


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


_PRIOR_WORKOUT_4_DAYS = {"days": [{"name": f"Day {i}"} for i in range(1, 5)]}


def test_resolve_expected_day_count_explicit_overrides_add_day_arithmetic() -> None:
    """An explicit target wins even for a jump ADD_DAY's +1 could never produce (4 -> 6)."""
    operation = EditOperation(operation="ADD_DAY")
    expected = resolve_expected_day_count(
        operation,
        _PRIOR_WORKOUT_4_DAYS,
        {"days_per_week": 6},
        days_per_week_explicit=True,
    )
    assert expected == 6


def test_resolve_expected_day_count_explicit_overrides_other_unchanged() -> None:
    """OTHER normally keeps the previous count; an explicit target must still win (4 -> 3)."""
    operation = EditOperation(operation="OTHER")
    expected = resolve_expected_day_count(
        operation,
        _PRIOR_WORKOUT_4_DAYS,
        {"days_per_week": 3},
        days_per_week_explicit=True,
    )
    assert expected == 3


def test_resolve_expected_day_count_non_explicit_add_day_unchanged() -> None:
    """Regression: without an explicit target, ADD_DAY still just adds one, as before."""
    operation = EditOperation(operation="ADD_DAY")
    expected = resolve_expected_day_count(
        operation,
        _PRIOR_WORKOUT_4_DAYS,
        {"days_per_week": 4},
        days_per_week_explicit=False,
    )
    assert expected == 5


def test_resolve_expected_day_count_non_explicit_remove_day_unchanged() -> None:
    """Regression: without an explicit target, REMOVE_DAY still just subtracts one."""
    operation = EditOperation(operation="REMOVE_DAY")
    expected = resolve_expected_day_count(
        operation,
        _PRIOR_WORKOUT_4_DAYS,
        {"days_per_week": 4},
        days_per_week_explicit=False,
    )
    assert expected == 3


def test_resolve_expected_day_count_non_explicit_other_keeps_previous() -> None:
    """Regression: the original bug case -- OTHER with no explicit target keeps the old count."""
    operation = EditOperation(operation="OTHER")
    expected = resolve_expected_day_count(
        operation,
        _PRIOR_WORKOUT_4_DAYS,
        {"days_per_week": 4},
        days_per_week_explicit=False,
    )
    assert expected == 4
