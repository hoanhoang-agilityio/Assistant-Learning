"""Tests for the availability rule: whether the user can train the plan, slot by slot."""

from src.enums import (
    ActivityLevel,
    BodyRegion,
    DifficultyLevel,
    EquipmentType,
    FitnessGoal,
    MovementPattern,
    MuscleGroup,
    Sex,
)
from src.schemas import (
    CheckName,
    Exercise,
    ExerciseSlot,
    MacroTargets,
    PlanDay,
    PlannedExercise,
    Severity,
    TrainingPlan,
    UserEquipment,
    UserProfile,
    WorkoutDayTemplate,
    WorkoutTemplate,
)
from src.verification.deterministic.availability import (
    check_availability,
)
from src.verification.deterministic.context import PlanContext

BENCH_PRESS = Exercise(
    id="ex-bench-press",
    name="Barbell bench press",
    body_region=BodyRegion.UPPER,
    primary_muscles=[MuscleGroup.CHEST],
    secondary_muscles=[MuscleGroup.TRICEPS],
    movement_pattern=MovementPattern.HORIZONTAL_PUSH,
    difficulty=DifficultyLevel.INTERMEDIATE,
    equipment=[EquipmentType.BARBELL, EquipmentType.BENCH],
)

PUSH_UP = Exercise(
    id="ex-push-up",
    name="Push-up",
    body_region=BodyRegion.UPPER,
    primary_muscles=[MuscleGroup.CHEST],
    movement_pattern=MovementPattern.HORIZONTAL_PUSH,
    difficulty=DifficultyLevel.BEGINNER,
    equipment=[EquipmentType.BODYWEIGHT],
)

DUMBBELL_FLY = Exercise(
    id="ex-dumbbell-fly",
    name="Dumbbell fly",
    body_region=BodyRegion.UPPER,
    primary_muscles=[MuscleGroup.CHEST],
    movement_pattern=MovementPattern.HORIZONTAL_ADDUCTION,
    difficulty=DifficultyLevel.BEGINNER,
    equipment=[EquipmentType.DUMBBELL],
)

LATERAL_RAISE = Exercise(
    id="ex-lateral-raise",
    name="Dumbbell lateral raise",
    body_region=BodyRegion.UPPER,
    primary_muscles=[MuscleGroup.SIDE_DELTS],
    movement_pattern=MovementPattern.ABDUCTION,
    difficulty=DifficultyLevel.BEGINNER,
    equipment=[EquipmentType.DUMBBELL],
)

SKULL_CRUSHER = Exercise(
    id="ex-skull-crusher",
    name="Lying triceps extension",
    body_region=BodyRegion.UPPER,
    primary_muscles=[MuscleGroup.TRICEPS],
    movement_pattern=MovementPattern.ELBOW_EXTENSION,
    difficulty=DifficultyLevel.INTERMEDIATE,
    equipment=[EquipmentType.DUMBBELL],
)

BACK_SQUAT = Exercise(
    id="ex-back-squat",
    name="Barbell back squat",
    body_region=BodyRegion.LOWER,
    primary_muscles=[MuscleGroup.QUADS],
    movement_pattern=MovementPattern.SQUAT,
    difficulty=DifficultyLevel.INTERMEDIATE,
    equipment=[EquipmentType.BARBELL],
)

CATALOGUE = {
    exercise.id: exercise
    for exercise in (
        BENCH_PRESS,
        PUSH_UP,
        DUMBBELL_FLY,
        LATERAL_RAISE,
        SKULL_CRUSHER,
        BACK_SQUAT,
    )
}

CHEST_SLOT = ExerciseSlot(
    slot_id="d1-s1",
    target_muscles=[MuscleGroup.CHEST],
    allowed_movement_patterns=[MovementPattern.HORIZONTAL_PUSH],
    required_body_region=BodyRegion.UPPER,
)

REAR_DELT_SLOT = ExerciseSlot(
    slot_id="d1-s2",
    target_muscles=[MuscleGroup.REAR_DELTS],
    excluded_movement_patterns=[MovementPattern.HORIZONTAL_PUSH],
)

TEMPLATE = WorkoutTemplate(
    id="tpl-upper",
    name="Upper",
    goals=[FitnessGoal.FAT_LOSS],
    training_days=[
        WorkoutDayTemplate(
            day_number=1,
            name="Upper",
            body_region=BodyRegion.UPPER,
            exercise_slots=[CHEST_SLOT, REAR_DELT_SLOT],
        )
    ],
)

FULL_GYM = UserEquipment(
    equipment=[
        EquipmentType.BARBELL,
        EquipmentType.BENCH,
        EquipmentType.DUMBBELL,
    ]
)

HOME = UserEquipment(equipment=[EquipmentType.DUMBBELL])


def profile_with(equipment: UserEquipment = FULL_GYM) -> UserProfile:
    """A profile that differs only in what the user can train with."""
    return UserProfile(
        age=34,
        sex=Sex.MALE,
        height_cm=178.0,
        current_weight_kg=82.5,
        activity_level=ActivityLevel.MODERATE,
        goal=FitnessGoal.FAT_LOSS,
        training_days_per_week=2,
        available_equipment=equipment,
    )


def plan_of(*filled: tuple[str, str]) -> TrainingPlan:
    """A one-day plan, from (slot_id, exercise_id) pairs."""
    return TrainingPlan(
        template_id="tpl-upper",
        goal=FitnessGoal.FAT_LOSS,
        daily_calories=2200,
        macros=MacroTargets(protein_g=180, carbs_g=200, fat_g=66),
        training_days=[
            PlanDay(
                day_number=1,
                name="Upper",
                exercises=[
                    PlannedExercise(
                        slot_id=slot_id, exercise_id=exercise_id, sets=3, reps="8-12"
                    )
                    for slot_id, exercise_id in filled
                ],
            )
        ],
    )


def context_for(
    plan: TrainingPlan,
    *,
    equipment: UserEquipment = FULL_GYM,
    template: WorkoutTemplate | None = TEMPLATE,
) -> PlanContext:
    """A resolved context over the fixture template and catalogue."""
    return PlanContext(
        plan=plan,
        profile=profile_with(equipment),
        template=template,
        exercises=CATALOGUE,
    )


# --- Equipment --------------------------------------------------------------------------


def test_an_exercise_the_user_cannot_equip_fails_the_gate() -> None:
    """The plan is only worth writing if the user can carry it out on Monday."""
    context = context_for(plan_of(("d1-s1", "ex-bench-press")), equipment=HOME)

    [issue] = check_availability(context)

    assert issue.check is CheckName.AVAILABILITY
    assert issue.severity is Severity.ERROR
    assert issue.exercise_id == "ex-bench-press"


def test_the_message_names_what_is_missing_rather_than_what_is_needed() -> None:
    """The user owns a bench for nothing if the coach is told the whole list again."""
    context = context_for(plan_of(("d1-s1", "ex-bench-press")), equipment=HOME)

    [issue] = check_availability(context)

    assert "BARBELL, BENCH" in issue.message


def test_bodyweight_is_nobodys_to_own() -> None:
    """A push-up is available to a user whose equipment list is only a pair of dumbbells."""
    context = context_for(plan_of(("d1-s1", "ex-push-up")), equipment=HOME)

    assert check_availability(context) == []


def test_an_unasked_equipment_list_does_not_rule_everything_out() -> None:
    """An empty list is a profile nobody asked, not a user who owns nothing."""
    context = context_for(
        plan_of(("d1-s1", "ex-bench-press")), equipment=UserEquipment()
    )

    assert check_availability(context) == []


# --- Slot fit ---------------------------------------------------------------------------


def test_an_exercise_that_fills_its_slot_has_nothing_to_report() -> None:
    """The rule has to stay quiet on a good prescription or it fails every plan."""
    assert check_availability(context_for(plan_of(("d1-s1", "ex-bench-press")))) == []


def test_a_movement_pattern_the_slot_does_not_take_fails_the_gate() -> None:
    """A fly trains the chest the slot asked for, in a pattern it did not ask for."""
    context = context_for(plan_of(("d1-s1", "ex-dumbbell-fly")))

    [issue] = check_availability(context)

    assert "does not take" in issue.message


def test_an_excluded_pattern_fails_even_with_no_allowed_list() -> None:
    """A slot that names only what it refuses still refuses it."""
    slot = ExerciseSlot(
        slot_id="d1-s1", excluded_movement_patterns=[MovementPattern.HORIZONTAL_PUSH]
    )
    template = TEMPLATE.model_copy(deep=True)
    template.training_days[0].exercise_slots = [slot]
    context = context_for(plan_of(("d1-s1", "ex-push-up")), template=template)

    [issue] = check_availability(context)

    assert "does not take" in issue.message


def test_an_exercise_that_does_not_train_the_slots_muscle_fails_the_gate() -> None:
    """The rear-delt slot filled by a lateral raise: right region, wrong head."""
    context = context_for(plan_of(("d1-s2", "ex-lateral-raise")))

    [issue] = check_availability(context)

    assert issue.severity is Severity.ERROR
    assert "does not train REAR_DELTS" in issue.message


def test_training_the_slots_muscle_only_as_a_secondary_is_a_warning() -> None:
    """The day still gets the work, further down the exercise than the template intended."""
    slot = ExerciseSlot(
        slot_id="d1-s1",
        target_muscles=[MuscleGroup.TRICEPS],
        allowed_movement_patterns=[MovementPattern.HORIZONTAL_PUSH],
        required_body_region=BodyRegion.UPPER,
    )
    template = TEMPLATE.model_copy(deep=True)
    template.training_days[0].exercise_slots = [slot]
    context = context_for(plan_of(("d1-s1", "ex-bench-press")), template=template)

    [issue] = check_availability(context)

    assert issue.severity is Severity.WARNING
    assert "only as a secondary" in issue.message


def test_one_primary_hit_satisfies_a_slot_naming_several_muscles() -> None:
    """A slot asks for an exercise that covers its muscles, not for all of them at once."""
    slot = ExerciseSlot(
        slot_id="d1-s1",
        target_muscles=[MuscleGroup.CHEST, MuscleGroup.SHOULDERS],
        allowed_movement_patterns=[MovementPattern.HORIZONTAL_PUSH],
    )
    template = TEMPLATE.model_copy(deep=True)
    template.training_days[0].exercise_slots = [slot]

    assert (
        check_availability(
            context_for(plan_of(("d1-s1", "ex-bench-press")), template=template)
        )
        == []
    )


def test_a_slot_naming_no_muscles_accepts_any_of_them() -> None:
    """Not every slot is written for a muscle; some only constrain the movement."""
    slot = ExerciseSlot(
        slot_id="d1-s1", allowed_movement_patterns=[MovementPattern.HORIZONTAL_PUSH]
    )
    template = TEMPLATE.model_copy(deep=True)
    template.training_days[0].exercise_slots = [slot]

    assert (
        check_availability(
            context_for(plan_of(("d1-s1", "ex-push-up")), template=template)
        )
        == []
    )


def test_the_wrong_body_region_fails_the_gate() -> None:
    """An upper day filled with a squat is not the week the template describes."""
    slot = ExerciseSlot(
        slot_id="d1-s1",
        target_muscles=[MuscleGroup.QUADS],
        required_body_region=BodyRegion.UPPER,
    )
    template = TEMPLATE.model_copy(deep=True)
    template.training_days[0].exercise_slots = [slot]
    context = context_for(plan_of(("d1-s1", "ex-back-squat")), template=template)

    [issue] = check_availability(context)

    assert "requires UPPER" in issue.message


def test_an_exercise_that_misses_a_slot_every_way_is_reported_once() -> None:
    """A squat in a chest slot is wrong three ways over and right by a single swap."""
    context = context_for(plan_of(("d1-s1", "ex-back-squat")))

    [issue] = check_availability(context)

    assert "does not train CHEST" in issue.message


def test_an_error_is_never_displaced_by_a_warning() -> None:
    """The muscle finding is reported first, but not when it is the softer of the two."""
    slot = ExerciseSlot(
        slot_id="d1-s1",
        target_muscles=[MuscleGroup.TRICEPS],
        allowed_movement_patterns=[MovementPattern.ELBOW_EXTENSION],
    )
    template = TEMPLATE.model_copy(deep=True)
    template.training_days[0].exercise_slots = [slot]
    context = context_for(plan_of(("d1-s1", "ex-bench-press")), template=template)

    [issue] = check_availability(context)

    assert issue.severity is Severity.ERROR
    assert "does not take" in issue.message


def test_equipment_is_reported_alongside_a_slot_it_also_misses() -> None:
    """The two are independent: swapping for fit could still leave nothing to lift with."""
    context = context_for(plan_of(("d1-s1", "ex-back-squat")), equipment=HOME)

    assert len(check_availability(context)) == 2


# --- What the rule does not own ---------------------------------------------------------


def test_equipment_is_still_checked_when_the_template_does_not_resolve() -> None:
    """Whether the user owns a barbell has nothing to do with the template."""
    context = context_for(
        plan_of(("d1-s1", "ex-bench-press")), equipment=HOME, template=None
    )

    [issue] = check_availability(context)

    assert "BARBELL, BENCH" in issue.message


def test_a_slot_the_template_does_not_have_is_left_to_the_completeness_rule() -> None:
    """There is no slot to fit the exercise against, and one bad id is not two findings."""
    context = context_for(plan_of(("d1-s9", "ex-back-squat")))

    assert check_availability(context) == []


def test_an_exercise_that_resolves_to_nothing_is_left_to_the_completeness_rule() -> (
    None
):
    """There is no catalogue row to judge availability against."""
    context = context_for(plan_of(("d1-s1", "ex-invented")), equipment=HOME)

    assert check_availability(context) == []
