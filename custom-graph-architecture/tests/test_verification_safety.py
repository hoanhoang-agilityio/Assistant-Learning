"""Tests for the safety rule: what a user's injuries rule out of a finished plan."""

import pytest

from src.core.langgraph.verification.deterministic.context import PlanContext
from src.core.langgraph.verification.deterministic.safety import check_safety
from src.schemas import (
    ActivityLevel,
    BodyRegion,
    CheckName,
    DifficultyLevel,
    Exercise,
    FitnessGoal,
    Injury,
    InjuryStatus,
    MacroTargets,
    MovementPattern,
    MovementRestriction,
    MuscleGroup,
    PlanDay,
    PlannedExercise,
    RestrictionAction,
    Severity,
    Sex,
    TrainingPlan,
    UserProfile,
)

BENCH_PRESS = Exercise(
    id="ex-bench-press",
    name="Barbell bench press",
    body_region=BodyRegion.UPPER,
    primary_muscles=[MuscleGroup.CHEST],
    movement_pattern=MovementPattern.HORIZONTAL_PUSH,
    difficulty=DifficultyLevel.INTERMEDIATE,
    contraindications=[
        {
            "body_part": "shoulder",
            "movement_patterns": [MovementPattern.HORIZONTAL_PUSH],
            "reason": "Loads the anterior shoulder under a fixed bar path.",
        }
    ],
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

BASE_PROFILE = {
    "age": 34,
    "sex": Sex.MALE,
    "height_cm": 178.0,
    "current_weight_kg": 82.5,
    "activity_level": ActivityLevel.MODERATE,
    "goal": FitnessGoal.FAT_LOSS,
    "training_days_per_week": 2,
}


def injury(
    body_part: str,
    movement_pattern: MovementPattern | None = None,
    action: RestrictionAction = RestrictionAction.PROHIBITED,
    status: InjuryStatus = InjuryStatus.ACTIVE,
    reason: str | None = None,
) -> Injury:
    """An injury restricting one movement pattern, or none when the pattern is omitted."""
    restrictions = (
        []
        if movement_pattern is None
        else [
            MovementRestriction(
                movement_pattern=movement_pattern, action=action, reason=reason
            )
        ]
    )
    return Injury(body_part=body_part, status=status, restrictions=restrictions)


def plan_of(*exercise_ids: str) -> TrainingPlan:
    """A one-day plan prescribing the given exercises, one per slot."""
    return TrainingPlan(
        template_id="tpl-upper-lower",
        goal=FitnessGoal.FAT_LOSS,
        daily_calories=2200,
        macros=MacroTargets(protein_g=180, carbs_g=200, fat_g=66),
        training_days=[
            PlanDay(
                day_number=1,
                name="Upper",
                exercises=[
                    PlannedExercise(
                        slot_id=f"d1-s{index}",
                        exercise_id=exercise_id,
                        sets=3,
                        reps="8-12",
                    )
                    for index, exercise_id in enumerate(exercise_ids, start=1)
                ],
            )
        ],
    )


def context_for(plan: TrainingPlan, *injuries: Injury) -> PlanContext:
    """A resolved context over the fixture catalogue — no database, as the rules intend."""
    return PlanContext(
        plan=plan,
        profile=UserProfile(**BASE_PROFILE, injuries=list(injuries)),
        template=None,
        exercises=CATALOGUE,
    )


# --- Prohibited movement patterns -------------------------------------------------------


def test_an_exercise_whose_pattern_an_injury_prohibits_fails_the_gate() -> None:
    """The case the rule exists for: a plan that would have the user train through it."""
    context = context_for(
        plan_of("ex-bench-press"),
        injury("shoulder", MovementPattern.HORIZONTAL_PUSH),
    )

    [issue] = check_safety(context)

    assert issue.check is CheckName.SAFETY
    assert issue.severity is Severity.ERROR
    assert issue.exercise_id == "ex-bench-press"


def test_an_issue_locates_itself_in_the_plan() -> None:
    """The agent has to know which prescription to swap, not just that one is wrong."""
    context = context_for(
        plan_of("ex-cable-row", "ex-bench-press"),
        injury("shoulder", MovementPattern.HORIZONTAL_PUSH),
    )

    [issue] = check_safety(context)

    assert (issue.day_number, issue.slot_id) == (1, "d1-s2")


def test_the_reason_an_injury_gives_reaches_the_agent() -> None:
    """A restriction's reason is the part the coach cannot work out from the enums."""
    context = context_for(
        plan_of("ex-back-squat"),
        injury("knee", MovementPattern.SQUAT, reason="Meniscus tear, loaded flexion"),
    )

    [issue] = check_safety(context)

    assert "Meniscus tear, loaded flexion" in issue.message


def test_an_unrelated_pattern_is_left_alone() -> None:
    """A shoulder that rules out pressing does not rule out pulling."""
    context = context_for(
        plan_of("ex-cable-row"),
        injury("shoulder", MovementPattern.HORIZONTAL_PUSH),
    )

    assert check_safety(context) == []


# --- Contraindications ------------------------------------------------------------------


def test_a_contraindicated_exercise_fails_even_with_no_restriction_recorded() -> None:
    """The catalogue knows things the profile does not: an injury alone is enough."""
    context = context_for(plan_of("ex-bench-press"), injury("shoulder"))

    [issue] = check_safety(context)

    assert issue.severity is Severity.ERROR
    assert "contraindicated" in issue.message


def test_one_injury_is_worth_one_issue() -> None:
    """Contraindicated and prohibited is still a single swap; twice is noise."""
    context = context_for(
        plan_of("ex-bench-press"),
        injury("shoulder", MovementPattern.HORIZONTAL_PUSH),
    )

    assert len(check_safety(context)) == 1


def test_two_injuries_against_the_same_exercise_are_both_reported() -> None:
    """Swapping for the knee's sake could still leave the shoulder's objection standing."""
    context = context_for(
        plan_of("ex-back-squat"),
        injury("knee", MovementPattern.SQUAT),
        injury("lower back", MovementPattern.SQUAT),
    )

    assert len(check_safety(context)) == 2


# --- Severity ---------------------------------------------------------------------------


def test_a_limited_movement_is_a_warning_rather_than_a_failure() -> None:
    """A user who may train a pattern with care should not be left with no plan at all."""
    context = context_for(
        plan_of("ex-back-squat"),
        injury("knee", MovementPattern.SQUAT, action=RestrictionAction.LIMITED),
    )

    [issue] = check_safety(context)

    assert issue.severity is Severity.WARNING


def test_the_strictest_restriction_on_a_pattern_is_the_one_reported() -> None:
    """An injury listing a pattern twice must not be let off by its milder entry."""
    knee = Injury(
        body_part="knee",
        restrictions=[
            MovementRestriction(
                movement_pattern=MovementPattern.SQUAT,
                action=RestrictionAction.LIMITED,
            ),
            MovementRestriction(
                movement_pattern=MovementPattern.SQUAT,
                action=RestrictionAction.PROHIBITED,
            ),
        ],
    )
    context = context_for(plan_of("ex-back-squat"), knee)

    [issue] = check_safety(context)

    assert issue.severity is Severity.ERROR


def test_an_allowed_restriction_says_nothing() -> None:
    """ALLOWED is a note that the pattern was considered, not a finding."""
    context = context_for(
        plan_of("ex-back-squat"),
        injury("knee", MovementPattern.SQUAT, action=RestrictionAction.ALLOWED),
    )

    assert check_safety(context) == []


# --- What the rule does not own ---------------------------------------------------------


@pytest.mark.parametrize("status", [InjuryStatus.ACTIVE, InjuryStatus.RECOVERING])
def test_an_unresolved_injury_still_constrains_the_plan(status: InjuryStatus) -> None:
    """Recovering is not recovered; the restriction holds until the status says so."""
    context = context_for(
        plan_of("ex-back-squat"),
        injury("knee", MovementPattern.SQUAT, status=status),
    )

    assert len(check_safety(context)) == 1


def test_a_resolved_injury_no_longer_constrains_the_plan() -> None:
    """Past injuries stay on the profile; they stop filtering the catalogue."""
    context = context_for(
        plan_of("ex-back-squat"),
        injury("knee", MovementPattern.SQUAT, status=InjuryStatus.RESOLVED),
    )

    assert check_safety(context) == []


def test_a_user_with_no_injuries_has_nothing_to_check() -> None:
    """The common case has to cost nothing and find nothing."""
    assert check_safety(context_for(plan_of("ex-bench-press"))) == []


def test_an_exercise_that_resolves_to_nothing_is_left_to_the_completeness_rule() -> (
    None
):
    """There is no catalogue row to judge, and one invented id is not two findings."""
    context = context_for(plan_of("ex-invented"), injury("shoulder"))

    assert check_safety(context) == []
