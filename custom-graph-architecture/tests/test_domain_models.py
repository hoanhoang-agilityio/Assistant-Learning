"""Tests for the domain models: the constraints they enforce and the helpers on them."""

import pytest
from pydantic import ValidationError

from src.enums import (
    ActivityLevel,
    BodyRegion,
    DifficultyLevel,
    EquipmentType,
    FitnessGoal,
    InjuryStatus,
    MovementPattern,
    MuscleGroup,
    RestrictionAction,
    Sex,
)
from src.schemas import (
    Exercise,
    ExerciseSlot,
    Injury,
    MacroTargets,
    MovementRestriction,
    TrainingPlan,
    UserEquipment,
    UserProfile,
    WorkoutDayTemplate,
    WorkoutTemplate,
)
from src.services.profile import REQUIRED_PROFILE_FIELDS

BENCH_PRESS = Exercise(
    id="ex-bench-press",
    name="Barbell bench press",
    body_region=BodyRegion.UPPER,
    primary_muscles=[MuscleGroup.CHEST],
    secondary_muscles=[MuscleGroup.TRICEPS, MuscleGroup.SHOULDERS],
    movement_pattern=MovementPattern.HORIZONTAL_PUSH,
    difficulty=DifficultyLevel.INTERMEDIATE,
    equipment=[EquipmentType.BARBELL, EquipmentType.BENCH],
    contraindications=[
        {
            "body_part": "shoulder",
            "movement_patterns": [MovementPattern.HORIZONTAL_PUSH],
            "reason": "Loads the anterior shoulder under a fixed bar path.",
        }
    ],
)

CHEST_SLOT = ExerciseSlot(
    slot_id="d1-s1",
    target_muscles=[MuscleGroup.CHEST],
    allowed_movement_patterns=[MovementPattern.HORIZONTAL_PUSH],
    excluded_movement_patterns=[MovementPattern.ISOLATION],
)

SHOULDER_INJURY = Injury(
    body_part="shoulder",
    status=InjuryStatus.ACTIVE,
    restrictions=[
        MovementRestriction(
            movement_pattern=MovementPattern.HORIZONTAL_PUSH,
            action=RestrictionAction.PROHIBITED,
        )
    ],
)

BASE_PROFILE = {
    "age": 34,
    "sex": Sex.MALE,
    "height_cm": 178.0,
    "current_weight_kg": 82.5,
    "activity_level": ActivityLevel.MODERATE,
    "goal": FitnessGoal.FAT_LOSS,
    "training_days_per_week": 4,
}


# --- Enums ------------------------------------------------------------------------------


def test_enum_values_are_the_strings_that_get_stored() -> None:
    """Profiles live in a JSON store, so a member has to round-trip as its own name."""
    assert Sex.MALE == "MALE"
    assert FitnessGoal.FAT_LOSS == "FAT_LOSS"


def test_restriction_action_is_the_intended_set() -> None:
    """The spec's value table for this enum repeats InjuryStatus; the field text is right."""
    assert {action.value for action in RestrictionAction} == {
        "PROHIBITED",
        "LIMITED",
        "ALLOWED",
    }


# --- UserProfile ------------------------------------------------------------------------


def test_the_required_fields_are_the_ones_the_collection_loop_asks_for() -> None:
    """One definition of 'required', so the gate and the model cannot disagree."""
    assert REQUIRED_PROFILE_FIELDS == (
        "age",
        "sex",
        "height_cm",
        "current_weight_kg",
        "activity_level",
        "goal",
        "training_days_per_week",
    )


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("age", 12),
        ("age", 101),
        ("training_days_per_week", 0),
        ("training_days_per_week", 8),
        ("height_cm", 0),
        ("current_weight_kg", -1),
        ("target_weight_kg", 0),
    ],
)
def test_out_of_range_values_are_refused(field: str, value: float) -> None:
    """The bounds the extraction filter enforces are the model's own."""
    with pytest.raises(ValidationError):
        UserProfile(**(BASE_PROFILE | {field: value}))


def test_the_optional_parts_of_a_profile_default_to_empty() -> None:
    """A user with no injuries and no kit is a complete profile, not a partial one."""
    profile = UserProfile(**BASE_PROFILE)

    assert profile.injuries == []
    assert profile.preferences == []
    assert profile.available_equipment == UserEquipment()


def test_a_resolved_injury_stops_constraining_training() -> None:
    """A healed injury must not narrow the exercise pool for the rest of the user's life."""
    healed = SHOULDER_INJURY.model_copy(update={"status": InjuryStatus.RESOLVED})

    assert not healed.constrains_training
    assert not healed.prohibits(MovementPattern.HORIZONTAL_PUSH)


def test_prohibited_movements_come_from_unresolved_injuries_only() -> None:
    """This set is what the retrieval filter subtracts from the catalogue."""
    profile = UserProfile(
        **BASE_PROFILE,
        injuries=[
            SHOULDER_INJURY,
            SHOULDER_INJURY.model_copy(update={"status": InjuryStatus.RESOLVED}),
        ],
    )

    assert profile.prohibited_movements() == {MovementPattern.HORIZONTAL_PUSH}
    assert len(profile.active_injuries) == 1


def test_a_limited_restriction_is_not_a_prohibition() -> None:
    """LIMITED means coach around it, not exclude it."""
    limited = Injury(
        body_part="knee",
        restrictions=[
            MovementRestriction(
                movement_pattern=MovementPattern.SQUAT,
                action=RestrictionAction.LIMITED,
            )
        ],
    )

    assert not limited.prohibits(MovementPattern.SQUAT)


def test_equipment_support_is_a_subset_check() -> None:
    """An exercise is only available if every piece of kit it needs is."""
    home = UserEquipment(equipment=[EquipmentType.DUMBBELL, EquipmentType.BENCH])

    assert home.supports([EquipmentType.DUMBBELL])
    assert not home.supports([EquipmentType.DUMBBELL, EquipmentType.BARBELL])


# --- Exercise ---------------------------------------------------------------------------


def test_an_exercise_needs_at_least_one_primary_muscle() -> None:
    """A row with no primary muscle can never satisfy a slot's target muscles."""
    with pytest.raises(ValidationError):
        Exercise.model_validate(BENCH_PRESS.model_dump() | {"primary_muscles": []})


def test_a_contraindication_matches_the_injured_body_part() -> None:
    """The safety check turns on this, so the comparison must not be case sensitive."""
    assert BENCH_PRESS.is_contraindicated_for("Shoulder")
    assert not BENCH_PRESS.is_contraindicated_for("knee")


def test_a_contraindication_with_no_patterns_rules_the_exercise_out_entirely() -> None:
    """An unqualified contraindication is a blanket one."""
    blanket = Exercise.model_validate(
        BENCH_PRESS.model_dump() | {"contraindications": [{"body_part": "shoulder"}]}
    )

    assert blanket.is_contraindicated_for("shoulder")


# --- Template and slots -------------------------------------------------------------------


def test_a_slot_accepts_only_its_allowed_patterns() -> None:
    """This is the filter that turns a template requirement into a catalogue query."""
    assert CHEST_SLOT.accepts_pattern(MovementPattern.HORIZONTAL_PUSH)
    assert not CHEST_SLOT.accepts_pattern(MovementPattern.SQUAT)


def test_an_excluded_pattern_wins_over_an_allowed_one() -> None:
    """Exclusions are the safety half of the filter, so they cannot be overridden."""
    conflicted = CHEST_SLOT.model_copy(
        update={
            "allowed_movement_patterns": [MovementPattern.ISOLATION],
            "excluded_movement_patterns": [MovementPattern.ISOLATION],
        }
    )

    assert not conflicted.accepts_pattern(MovementPattern.ISOLATION)


def test_a_slot_with_no_allowed_patterns_accepts_anything_not_excluded() -> None:
    """An open slot is the default, so an empty list must not mean 'nothing fits'."""
    open_slot = ExerciseSlot(
        slot_id="d1-s2", excluded_movement_patterns=[MovementPattern.CARRY]
    )

    assert open_slot.accepts_pattern(MovementPattern.HINGE)
    assert not open_slot.accepts_pattern(MovementPattern.CARRY)


def test_a_training_day_needs_at_least_one_slot() -> None:
    """A day requiring nothing would pass verification while prescribing nothing."""
    with pytest.raises(ValidationError):
        WorkoutDayTemplate(
            day_number=1,
            name="Upper Push",
            body_region=BodyRegion.UPPER,
            exercise_slots=[],
        )


def test_a_template_lists_every_slot_it_requires_to_be_filled() -> None:
    """The gate checks the plan against this set, so it has to span every day."""
    template = WorkoutTemplate(
        id="tpl-1",
        name="Upper/Lower",
        goals=[FitnessGoal.MUSCLE_GAIN],
        training_days=[
            WorkoutDayTemplate(
                day_number=1,
                name="Upper",
                body_region=BodyRegion.UPPER,
                exercise_slots=[CHEST_SLOT],
            ),
            WorkoutDayTemplate(
                day_number=2,
                name="Lower",
                body_region=BodyRegion.LOWER,
                exercise_slots=[ExerciseSlot(slot_id="d2-s1")],
            ),
        ],
    )

    assert template.slot_ids() == {"d1-s1", "d2-s1"}
    assert len(template.slots()) == 2
    assert template.days_per_week == 2


# --- Plan -------------------------------------------------------------------------------


def _plan(**overrides: object) -> TrainingPlan:
    """A minimal valid plan."""
    return TrainingPlan(
        **{
            "template_id": "tpl-1",
            "goal": FitnessGoal.FAT_LOSS,
            "daily_calories": 2200,
            "macros": {"protein_g": 165.0, "carbs_g": 220.0, "fat_g": 61.0},
            "training_days": [
                {
                    "day_number": 1,
                    "name": "Upper",
                    "exercises": [
                        {
                            "slot_id": "d1-s1",
                            "exercise_id": "ex-bench-press",
                            "sets": 4,
                            "reps": "8-12",
                        }
                    ],
                }
            ],
            **overrides,
        }
    )


def test_a_prescription_carries_only_ids_and_the_prescription() -> None:
    """A copied name or equipment list could contradict what exercise_id points at."""
    assert set(_plan().training_days[0].exercises[0].model_fields_set) <= {
        "slot_id",
        "exercise_id",
        "sets",
        "reps",
        "rest_seconds",
        "notes",
    }


def test_a_plan_records_the_template_it_was_built_from() -> None:
    """Without it the gate cannot re-resolve the slots the plan claims to fill."""
    assert _plan().template_id == "tpl-1"


def test_every_filled_slot_is_reported_including_duplicates() -> None:
    """Two prescriptions for one slot is a defect the gate has to be able to see."""
    plan = _plan(
        training_days=[
            {
                "day_number": 1,
                "name": "Upper",
                "exercises": [
                    {
                        "slot_id": "d1-s1",
                        "exercise_id": "ex-a",
                        "sets": 3,
                        "reps": "10",
                    },
                    {
                        "slot_id": "d1-s1",
                        "exercise_id": "ex-b",
                        "sets": 3,
                        "reps": "10",
                    },
                ],
            }
        ]
    )

    assert plan.filled_slot_ids() == ["d1-s1", "d1-s1"]


def test_macros_report_the_calories_they_come_to() -> None:
    """The macro consistency check compares this against daily_calories."""
    assert MacroTargets(protein_g=165, carbs_g=220, fat_g=61).calories == pytest.approx(
        165 * 4 + 220 * 4 + 61 * 9
    )


@pytest.mark.parametrize(
    "override",
    [
        {"training_days": []},
        {"daily_calories": 0},
    ],
)
def test_a_plan_missing_its_substance_is_refused(override: dict) -> None:
    """Schema completeness is enforced here so the gate does not have to restate it."""
    with pytest.raises(ValidationError):
        _plan(**override)


def test_a_day_with_no_exercises_is_refused() -> None:
    """A rest day is an absent day, not a training day with nothing in it."""
    with pytest.raises(ValidationError):
        _plan(training_days=[{"day_number": 1, "name": "Upper", "exercises": []}])


def test_zero_sets_is_refused() -> None:
    """A prescription of no work would pass a volume check by doing nothing."""
    with pytest.raises(ValidationError):
        _plan(
            training_days=[
                {
                    "day_number": 1,
                    "name": "Upper",
                    "exercises": [
                        {"slot_id": "s", "exercise_id": "e", "sets": 0, "reps": "10"}
                    ],
                }
            ]
        )
