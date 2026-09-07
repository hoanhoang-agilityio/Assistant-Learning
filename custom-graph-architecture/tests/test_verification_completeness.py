"""Tests for the completeness rule: whether a plan actually fills the template it names."""

from src.enums import (
    ActivityLevel,
    BodyRegion,
    DifficultyLevel,
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
    UserProfile,
    WorkoutDayTemplate,
    WorkoutTemplate,
)
from src.verification.deterministic.completeness import (
    check_completeness,
)
from src.verification.deterministic.context import PlanContext

BENCH_PRESS = Exercise(
    id="ex-bench-press",
    name="Barbell bench press",
    body_region=BodyRegion.UPPER,
    primary_muscles=[MuscleGroup.CHEST],
    movement_pattern=MovementPattern.HORIZONTAL_PUSH,
    difficulty=DifficultyLevel.INTERMEDIATE,
)

CABLE_ROW = Exercise(
    id="ex-cable-row",
    name="Seated cable row",
    body_region=BodyRegion.UPPER,
    primary_muscles=[MuscleGroup.BACK],
    movement_pattern=MovementPattern.HORIZONTAL_PULL,
    difficulty=DifficultyLevel.BEGINNER,
)

BACK_SQUAT = Exercise(
    id="ex-back-squat",
    name="Barbell back squat",
    body_region=BodyRegion.LOWER,
    primary_muscles=[MuscleGroup.QUADS],
    movement_pattern=MovementPattern.SQUAT,
    difficulty=DifficultyLevel.INTERMEDIATE,
)

CATALOGUE = {exercise.id: exercise for exercise in (BENCH_PRESS, CABLE_ROW, BACK_SQUAT)}

# Two days, two slots on day 1 and one on day 2 — enough to tell "unfilled", "duplicated"
# and "filled on the wrong day" apart.
TEMPLATE = WorkoutTemplate(
    id="tpl-upper-lower",
    name="Upper / Lower",
    goals=[FitnessGoal.FAT_LOSS],
    training_days=[
        WorkoutDayTemplate(
            day_number=1,
            name="Upper",
            body_region=BodyRegion.UPPER,
            exercise_slots=[
                ExerciseSlot(
                    slot_id="d1-s1",
                    exercise_id="ex-bench-press",
                    target_muscles=[MuscleGroup.CHEST],
                ),
                ExerciseSlot(
                    slot_id="d1-s2",
                    exercise_id="ex-cable-row",
                    target_muscles=[MuscleGroup.BACK],
                ),
            ],
        ),
        WorkoutDayTemplate(
            day_number=2,
            name="Lower",
            body_region=BodyRegion.LOWER,
            exercise_slots=[
                ExerciseSlot(
                    slot_id="d2-s1",
                    exercise_id="ex-back-squat",
                    target_muscles=[MuscleGroup.QUADS],
                )
            ],
        ),
    ],
)

PROFILE = UserProfile(
    age=34,
    sex=Sex.MALE,
    height_cm=178.0,
    current_weight_kg=82.5,
    activity_level=ActivityLevel.MODERATE,
    goal=FitnessGoal.FAT_LOSS,
    training_days_per_week=2,
)


def day(day_number: int, name: str, *filled: tuple[str, str]) -> PlanDay:
    """One plan day, from (slot_id, exercise_id) pairs."""
    return PlanDay(
        day_number=day_number,
        name=name,
        exercises=[
            PlannedExercise(
                slot_id=slot_id, exercise_id=exercise_id, sets=3, reps="8-12"
            )
            for slot_id, exercise_id in filled
        ],
    )


def plan_of(*days: PlanDay, template_id: str = "tpl-upper-lower") -> TrainingPlan:
    """A plan over the given days, naming the fixture template unless told otherwise."""
    return TrainingPlan(
        template_id=template_id,
        goal=FitnessGoal.FAT_LOSS,
        daily_calories=2200,
        macros=MacroTargets(protein_g=180, carbs_g=200, fat_g=66),
        training_days=list(days),
    )


def complete_plan() -> TrainingPlan:
    """A plan that fills the fixture template exactly."""
    return plan_of(
        day(1, "Upper", ("d1-s1", "ex-bench-press"), ("d1-s2", "ex-cable-row")),
        day(2, "Lower", ("d2-s1", "ex-back-squat")),
    )


def context_for(
    plan: TrainingPlan, *, template: WorkoutTemplate | None = TEMPLATE
) -> PlanContext:
    """A resolved context over the fixture template and catalogue."""
    return PlanContext(
        plan=plan, profile=PROFILE, template=template, exercises=CATALOGUE
    )


# --- The plan that is right -------------------------------------------------------------


def test_a_plan_that_fills_its_template_exactly_has_nothing_to_report() -> None:
    """The rule has to stay quiet on a good plan or it fails every plan."""
    assert check_completeness(context_for(complete_plan())) == []


# --- Slots ------------------------------------------------------------------------------


def test_an_unfilled_slot_fails_the_gate() -> None:
    """A template slot with no exercise is a plan the user cannot train."""
    plan = plan_of(
        day(1, "Upper", ("d1-s1", "ex-bench-press")),
        day(2, "Lower", ("d2-s1", "ex-back-squat")),
    )

    [issue] = check_completeness(context_for(plan))

    assert issue.check is CheckName.COMPLETENESS
    assert issue.severity is Severity.ERROR
    assert (issue.day_number, issue.slot_id) == (1, "d1-s2")


def test_a_slot_the_template_does_not_have_fails_the_gate() -> None:
    """The agent inventing a slot is the same failure as inventing an exercise."""
    plan = plan_of(
        day(
            1,
            "Upper",
            ("d1-s1", "ex-bench-press"),
            ("d1-s2", "ex-cable-row"),
            ("d1-s3", "ex-bench-press"),
        ),
        day(2, "Lower", ("d2-s1", "ex-back-squat")),
    )

    [issue] = check_completeness(context_for(plan))

    assert issue.slot_id == "d1-s3"
    assert "no slot" in issue.message


def test_a_slot_filled_on_the_wrong_day_says_where_it_belongs() -> None:
    """The exercise may be right and only the day wrong; 'unknown slot' would mislead."""
    plan = plan_of(
        day(1, "Upper", ("d1-s1", "ex-bench-press"), ("d1-s2", "ex-cable-row")),
        day(2, "Lower", ("d2-s1", "ex-back-squat"), ("d1-s1", "ex-bench-press")),
    )

    issues = check_completeness(context_for(plan))
    misplaced = [issue for issue in issues if issue.day_number == 2]

    assert len(misplaced) == 1
    assert "belongs to day 1" in misplaced[0].message


def test_a_slot_filled_twice_fails_the_gate() -> None:
    """Two exercises against one slot doubles the day's volume behind the template."""
    plan = plan_of(
        day(1, "Upper", ("d1-s1", "ex-bench-press"), ("d1-s1", "ex-cable-row")),
        day(2, "Lower", ("d2-s1", "ex-back-squat")),
    )

    issues = check_completeness(context_for(plan))
    duplicated = [issue for issue in issues if "filled 2 times" in issue.message]

    assert [issue.slot_id for issue in duplicated] == ["d1-s1"]


# --- Days -------------------------------------------------------------------------------


def test_a_missing_training_day_fails_the_gate() -> None:
    """A template day the plan skipped, reported once rather than per slot it left empty."""
    plan = plan_of(
        day(1, "Upper", ("d1-s1", "ex-bench-press"), ("d1-s2", "ex-cable-row"))
    )

    issues = check_completeness(context_for(plan))
    [missing] = [issue for issue in issues if issue.day_number == 2]

    assert missing.field == "training_days"


def test_a_day_the_template_does_not_have_is_reported_once() -> None:
    """Its slots are unknown too, but the extra day is the finding that explains them."""
    plan = plan_of(
        day(1, "Upper", ("d1-s1", "ex-bench-press"), ("d1-s2", "ex-cable-row")),
        day(2, "Lower", ("d2-s1", "ex-back-squat")),
        day(3, "Extra", ("d3-s1", "ex-bench-press")),
    )

    issues = check_completeness(context_for(plan))
    [extra] = [issue for issue in issues if issue.day_number == 3]

    assert "not in template" in extra.message


def test_a_repeated_day_number_fails_the_gate() -> None:
    """Two day 1s is not a five-day week; the numbering is what orders the plan."""
    plan = plan_of(
        day(1, "Upper", ("d1-s1", "ex-bench-press"), ("d1-s2", "ex-cable-row")),
        day(1, "Upper again", ("d1-s1", "ex-bench-press"), ("d1-s2", "ex-cable-row")),
        day(2, "Lower", ("d2-s1", "ex-back-squat")),
    )

    issues = check_completeness(context_for(plan))

    assert any("appears 2 times" in issue.message for issue in issues)


# --- Exercises and template ids ---------------------------------------------------------


def test_an_exercise_the_catalogue_does_not_hold_fails_the_gate() -> None:
    """The anti-hallucination check: the coach may only prescribe what it was handed."""
    plan = plan_of(
        day(1, "Upper", ("d1-s1", "ex-invented"), ("d1-s2", "ex-cable-row")),
        day(2, "Lower", ("d2-s1", "ex-back-squat")),
    )

    [issue] = check_completeness(context_for(plan))

    assert issue.exercise_id == "ex-invented"
    assert "load_exercise" in issue.message


def test_a_template_that_does_not_resolve_fails_the_gate() -> None:
    """Nothing downstream can be judged, so the plan cannot be allowed to pass."""
    context = context_for(complete_plan(), template=None)

    [issue] = check_completeness(context)

    assert issue.field == "template_id"
    assert "tpl-upper-lower" in issue.message


def test_an_unresolved_template_does_not_hide_an_invented_exercise() -> None:
    """The catalogue check needs no template, and both are worth one revision."""
    plan = plan_of(day(1, "Upper", ("d1-s1", "ex-invented")))

    issues = check_completeness(context_for(plan, template=None))

    assert {issue.field for issue in issues} == {"template_id", "training_days", None}
    assert any(issue.exercise_id == "ex-invented" for issue in issues)
