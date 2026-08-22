"""Tests for the seeded training catalogue.

The file-level tests run anywhere; the ones that read Postgres are marked ``integration``.
"""

import collections
import json
from pathlib import Path

import pytest
from sqlmodel import func, select

from src.models.catalogue import Exercise as ExerciseRow
from src.models.catalogue import WorkoutTemplate as TemplateRow
from src.schemas import (
    BodyRegion,
    Exercise,
    MovementPattern,
    MuscleGroup,
    WorkoutTemplate,
)
from src.services.database import session_factory

DATA_DIR = Path("data")


@pytest.fixture(scope="module")
def exercises() -> list[Exercise]:
    """The exercise catalogue as the domain model sees it."""
    rows = json.loads((DATA_DIR / "exercises.json").read_text())
    return [Exercise.model_validate(row) for row in rows]


@pytest.fixture(scope="module")
def templates() -> list[WorkoutTemplate]:
    """The workout templates as the domain model sees it."""
    rows = json.loads((DATA_DIR / "templates.json").read_text())
    return [WorkoutTemplate.model_validate(row) for row in rows]


# --- The files ---------------------------------------------------------------------------


def test_the_catalogue_validates_against_the_domain_models(
    exercises, templates
) -> None:
    """The seed is only useful if it is the shape the tools hand to the agent."""
    assert len(exercises) == 103
    assert len(templates) == 5


def test_exercise_ids_are_unique(exercises) -> None:
    """A prescription resolves by id, so a duplicate would resolve to either row."""
    assert len({exercise.id for exercise in exercises}) == len(exercises)


def test_slot_ids_are_unique_within_a_template(templates) -> None:
    """The gate checks each slot was filled once; duplicates would make that unanswerable."""
    for template in templates:
        slot_ids = [slot.slot_id for slot in template.slots()]
        assert len(set(slot_ids)) == len(slot_ids), template.id


def test_every_exercise_has_a_muscle_and_a_region(exercises) -> None:
    """Neither is in the source data; both are derived, so both need checking."""
    assert all(exercise.primary_muscles for exercise in exercises)
    assert all(exercise.body_region in BodyRegion for exercise in exercises)


def test_core_exercises_are_classified_by_what_they_train(exercises) -> None:
    """Region is derived from the primary muscles, so abs work must land in CORE."""
    abs_work = [
        exercise
        for exercise in exercises
        if exercise.primary_muscles == [MuscleGroup.ABS]
    ]

    assert abs_work
    assert all(exercise.body_region is BodyRegion.CORE for exercise in abs_work)


def test_isolation_patterns_stayed_distinct(exercises) -> None:
    """Collapsed into one bucket, a biceps slot and a calf slot would be the same query."""
    patterns = {exercise.movement_pattern for exercise in exercises}

    assert MovementPattern.ELBOW_FLEXION in patterns
    assert MovementPattern.CALF_RAISE in patterns
    assert MovementPattern.ABDUCTION in patterns
    assert MovementPattern.REAR_DELT_PULL in patterns


def test_delt_heads_stayed_distinct(exercises) -> None:
    """A rear-delt slot filled by a lateral raise is a wrong prescription."""
    muscles = {muscle for exercise in exercises for muscle in exercise.primary_muscles}

    assert {MuscleGroup.REAR_DELTS, MuscleGroup.SIDE_DELTS} <= muscles


# --- The catalogue can actually satisfy the templates ---------------------------------------


def test_every_slot_in_every_template_has_a_candidate(exercises, templates) -> None:
    """An unfillable slot fails every plan built from that template, by design."""
    by_pattern = collections.Counter(
        exercise.movement_pattern for exercise in exercises
    )

    unfillable = [
        (template.id, slot.slot_id, pattern)
        for template in templates
        for slot in template.slots()
        for pattern in slot.allowed_movement_patterns
        if by_pattern[pattern] == 0
    ]

    assert unfillable == []


def test_slots_carry_the_volume_the_template_prescribes(templates) -> None:
    """Sets and reps come from the template, so the volume check has a target to compare."""
    slots = [slot for template in templates for slot in template.slots()]

    assert all(slot.sets and slot.rep_range for slot in slots)


def test_the_templates_span_the_training_weeks_a_user_can_ask_for(templates) -> None:
    """``load_template`` filters on this, and a gap means a user with no template."""
    assert {template.days_per_week for template in templates} == {2, 3, 4, 5}


def test_every_goal_has_a_template(templates) -> None:
    """A goal with no template leaves the coach agent nothing to build from."""
    covered = {goal for template in templates for goal in template.goals}

    assert len(covered) == 4


# --- The tables --------------------------------------------------------------------------


@pytest.mark.integration
async def test_the_seeded_rows_round_trip_through_the_domain_models(
    require_postgres: None, exercises, templates
) -> None:
    """The tools hand the agent domain models, so the row has to rebuild into one."""
    async with session_factory() as session:
        exercise_count = (
            await session.execute(select(func.count()).select_from(ExerciseRow))
        ).scalar()
        row = (
            await session.execute(
                select(ExerciseRow).where(ExerciseRow.id == "barbell_bench_press")
            )
        ).scalar_one()
        template = (
            await session.execute(
                select(TemplateRow).where(TemplateRow.id == "upper_lower_4day")
            )
        ).scalar_one()

    assert exercise_count == len(exercises)
    assert row.to_schema().movement_pattern is MovementPattern.HORIZONTAL_PUSH
    assert template.to_schema().days_per_week == 4


@pytest.mark.integration
async def test_days_per_week_is_stored_for_filtering(require_postgres: None) -> None:
    """It is derived on the model but a column here, because the query filters on it."""
    async with session_factory() as session:
        rows = (
            await session.execute(
                select(TemplateRow).where(TemplateRow.days_per_week == 3)
            )
        ).scalars()

    assert {row.id for row in rows} == {"full_body_3day", "push_pull_legs_3day"}
