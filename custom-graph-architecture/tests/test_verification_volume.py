"""Tests for the volume rule: whether the prescribed week is one a person could train."""

import pytest

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
from src.verification.deterministic.context import PlanContext
from src.verification.deterministic.volume import (
    MAX_SETS_PER_DAY,
    MAX_SETS_PER_EXERCISE,
    MAX_WEEKLY_SETS_PER_MUSCLE,
    check_volume,
)


def exercise(id: str, name: str, muscle: MuscleGroup, region: BodyRegion) -> Exercise:
    """A catalogue row that differs only in the muscle it trains."""
    return Exercise(
        id=id,
        name=name,
        body_region=region,
        primary_muscles=[muscle],
        movement_pattern=MovementPattern.ISOLATION,
        difficulty=DifficultyLevel.BEGINNER,
    )


CATALOGUE = {
    row.id: row
    for row in (
        exercise("ex-bench", "Bench press", MuscleGroup.CHEST, BodyRegion.UPPER),
        exercise("ex-incline", "Incline press", MuscleGroup.CHEST, BodyRegion.UPPER),
        exercise("ex-row", "Cable row", MuscleGroup.BACK, BodyRegion.UPPER),
        exercise("ex-squat", "Back squat", MuscleGroup.QUADS, BodyRegion.LOWER),
        exercise("ex-curl", "Leg curl", MuscleGroup.HAMSTRINGS, BodyRegion.LOWER),
        exercise("ex-calf", "Calf raise", MuscleGroup.CALVES, BodyRegion.LOWER),
    )
}

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
                    target_muscles=[MuscleGroup.CHEST],
                    sets=4,
                    rep_range=(8, 12),
                ),
                ExerciseSlot(
                    slot_id="d1-s2",
                    target_muscles=[MuscleGroup.BACK],
                    sets=4,
                    rep_range=(8, 12),
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
                    target_muscles=[MuscleGroup.QUADS],
                    sets=4,
                    rep_range=(8, 12),
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


def prescribe(
    slot_id: str, exercise_id: str, sets: int = 4, reps: str = "8-12"
) -> PlannedExercise:
    """One prescription, defaulting to what the fixture template asks for."""
    return PlannedExercise(
        slot_id=slot_id, exercise_id=exercise_id, sets=sets, reps=reps
    )


def plan_of(*days: PlanDay) -> TrainingPlan:
    """A plan over the given days."""
    return TrainingPlan(
        template_id="tpl-upper-lower",
        goal=FitnessGoal.FAT_LOSS,
        daily_calories=2200,
        macros=MacroTargets(protein_g=180, carbs_g=200, fat_g=66),
        training_days=list(days),
    )


def clean_plan(
    *,
    sets: int = 4,
    reps: str = "8-12",
) -> TrainingPlan:
    """A plan that fills the fixture template with exactly what it asks for."""
    return plan_of(
        PlanDay(
            day_number=1,
            name="Upper",
            exercises=[
                prescribe("d1-s1", "ex-bench", sets, reps),
                prescribe("d1-s2", "ex-row", sets, reps),
            ],
        ),
        PlanDay(
            day_number=2,
            name="Lower",
            exercises=[prescribe("d2-s1", "ex-squat", sets, reps)],
        ),
    )


def context_for(
    plan: TrainingPlan,
    *,
    profile: UserProfile = PROFILE,
    template: WorkoutTemplate | None = TEMPLATE,
) -> PlanContext:
    """A resolved context over the fixture template and catalogue."""
    return PlanContext(
        plan=plan, profile=profile, template=template, exercises=CATALOGUE
    )


def messages(plan: TrainingPlan, **kwargs: object) -> str:
    """Every message the rule produced, joined — for asserting on one finding among many."""
    return " | ".join(
        issue.message for issue in check_volume(context_for(plan, **kwargs))
    )


# --- The plan that is right -------------------------------------------------------------


def test_a_plan_that_prescribes_what_the_template_asks_has_nothing_to_report() -> None:
    """The rule has to stay quiet on a good plan or it fails every plan."""
    assert check_volume(context_for(clean_plan())) == []


# --- Schedule ---------------------------------------------------------------------------


def test_training_fewer_days_than_the_user_asked_for_is_a_warning() -> None:
    """find_template picks the closest week it has; the coach cannot conjure an exact one."""
    profile = PROFILE.model_copy(update={"training_days_per_week": 4})

    [issue] = check_volume(context_for(clean_plan(), profile=profile))

    assert issue.check is CheckName.VOLUME
    assert issue.severity is Severity.WARNING
    assert issue.field == "training_days"


# --- Reps -------------------------------------------------------------------------------


@pytest.mark.parametrize("reps", ["10", "8-12", " 8 - 12 "])
def test_a_rep_prescription_in_the_documented_format_is_accepted(reps: str) -> None:
    """A single number and a range are both what PlannedExercise.reps says it holds."""
    assert check_volume(context_for(clean_plan(reps=reps))) == []


@pytest.mark.parametrize("reps", ["AMRAP", "8 to 12", "12 each side", "", "12-8"])
def test_reps_that_do_not_parse_fail_the_gate(reps: str) -> None:
    """A prescription the plan cannot read is one the checks below it cannot read either."""
    issues = check_volume(context_for(clean_plan(reps=reps)))

    assert all(issue.severity is Severity.ERROR for issue in issues)
    assert "is not a rep prescription" in issues[0].message


def test_an_inhuman_number_of_reps_fails_the_gate() -> None:
    """Three digits is a typo, and the user is the one who would try to perform it."""
    assert "outside 1-50" in messages(clean_plan(reps="100"))


def test_reps_outside_the_slots_range_are_a_warning() -> None:
    """The range is what the template asked for; a coach may still have a reason."""
    issues = check_volume(context_for(clean_plan(reps="20")))

    assert [issue.severity for issue in issues] == [Severity.WARNING] * 3
    assert "falls outside the 8-12 range" in issues[0].message


def test_reps_that_overlap_the_slots_range_are_accepted() -> None:
    """Shading a range is programming; missing it entirely is worth a word."""
    assert check_volume(context_for(clean_plan(reps="10-15"))) == []


# --- Sets -------------------------------------------------------------------------------


def test_sets_the_template_did_not_ask_for_are_a_warning() -> None:
    """Three sets where the slot said four is a judgment call, not a broken plan."""
    issues = check_volume(context_for(clean_plan(sets=3)))

    assert any("asks for 4 sets and the plan prescribes 3" in i.message for i in issues)
    assert all(issue.severity is Severity.WARNING for issue in issues)


def test_too_many_sets_of_one_exercise_fails_the_gate() -> None:
    """Past this the number stops being a prescription anyone would follow."""
    plan = plan_of(
        PlanDay(
            day_number=1,
            name="Upper",
            exercises=[prescribe("d1-s1", "ex-bench", MAX_SETS_PER_EXERCISE + 1)],
        )
    )

    assert "sets of one exercise is past the 10" in messages(plan)


def test_a_session_longer_than_an_evening_fails_the_gate() -> None:
    """Day volume is capped whatever the individual exercises look like."""
    plan = plan_of(
        PlanDay(
            day_number=1,
            name="Everything",
            exercises=[
                prescribe("d1-s1", "ex-bench", 8),
                prescribe("d1-s2", "ex-row", 8),
                prescribe("x-1", "ex-squat", 8),
                prescribe("x-2", "ex-curl", 8),
            ],
        )
    )

    assert f"32 working sets, past the {MAX_SETS_PER_DAY}" in messages(plan)


# --- Weekly volume ----------------------------------------------------------------------


def test_burying_one_muscle_across_the_week_fails_the_gate() -> None:
    """No single day is over the cap; the muscle still takes 32 sets a week."""
    plan = plan_of(
        PlanDay(
            day_number=1,
            name="Chest",
            exercises=[
                prescribe("d1-s1", "ex-bench", 8),
                prescribe("x-1", "ex-incline", 8),
            ],
        ),
        PlanDay(
            day_number=2,
            name="Chest again",
            exercises=[
                prescribe("x-2", "ex-bench", 8),
                prescribe("x-3", "ex-incline", 8),
            ],
        ),
    )

    assert (
        f"CHEST gets 32 working sets a week, past the {MAX_WEEKLY_SETS_PER_MUSCLE}"
        in (messages(plan))
    )


def test_a_muscle_the_template_trains_but_the_plan_barely_does_is_a_warning() -> None:
    """One set of back a week is not the upper day the template described."""
    plan = plan_of(
        PlanDay(
            day_number=1,
            name="Upper",
            exercises=[prescribe("d1-s1", "ex-bench"), prescribe("d1-s2", "ex-row", 1)],
        ),
        PlanDay(day_number=2, name="Lower", exercises=[prescribe("d2-s1", "ex-squat")]),
    )

    assert "BACK gets 1 working set a week where the template asks for 4" in messages(
        plan
    )


def test_trimming_a_set_from_every_slot_is_not_an_underdone_week() -> None:
    """A fixed weekly floor would flag every low-frequency template; the template rules."""
    assert not any(
        "working sets a week where" in issue.message
        for issue in check_volume(context_for(clean_plan(sets=3)))
    )


def test_a_muscle_the_template_never_undertook_to_train_is_not_missed() -> None:
    """A plan is not short of calf work it never set out to do."""
    assert "CALVES" not in messages(clean_plan())


# --- What the rule does not own ---------------------------------------------------------


def test_the_caps_still_apply_when_the_template_does_not_resolve() -> None:
    """How long a session is has nothing to do with which template it came from."""
    plan = plan_of(
        PlanDay(
            day_number=1,
            name="Upper",
            exercises=[prescribe("d1-s1", "ex-bench", MAX_SETS_PER_EXERCISE + 1)],
        )
    )

    assert "past the 10" in messages(plan, template=None)


def test_the_slot_comparisons_are_skipped_when_the_template_does_not_resolve() -> None:
    """There is nothing to compare the sets against, and 5.1 has already said so."""
    assert check_volume(context_for(clean_plan(sets=3), template=None)) == []


def test_an_exercise_that_resolves_to_nothing_is_not_counted() -> None:
    """Its muscles are unknown, so it can neither bury a muscle nor make up a shortfall."""
    plan = plan_of(
        PlanDay(
            day_number=1,
            name="Upper",
            exercises=[prescribe("d1-s1", "ex-invented"), prescribe("d1-s2", "ex-row")],
        ),
        PlanDay(day_number=2, name="Lower", exercises=[prescribe("d2-s1", "ex-squat")]),
    )

    assert "CHEST gets 0 working sets" in messages(plan)
