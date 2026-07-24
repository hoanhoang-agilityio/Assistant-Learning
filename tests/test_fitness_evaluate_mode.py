from pathlib import Path
from typing import Any

import pytest

from core.graph.run import create_initial_state
from core.subgraphs.fitness.graph import (
    _route_after_macros,
    _route_after_safety,
    build_fitness_subgraph,
    to_fitness_state,
)
from core.subgraphs.fitness.normalize import (
    SubmittedPlanExtraction,
    configure_submitted_plan_extractor,
    normalize_submitted_plan,
)
from core.subgraphs.fitness.schema import StructuredWorkout, WorkoutDay, WorkoutExercise
from core.vfs import VFS
from tests.helpers.planning import seed_execution_plan


@pytest.fixture
def complete_profile() -> dict[str, Any]:
    return {
        "age": 30,
        "sex": "male",
        "height_cm": 175,
        "current_weight_kg": 85.0,
        "activity_level": "gym_3x_week",
        "goal": "fat_loss",
        "days_per_week": 3,
    }


def _workout(day_count: int) -> StructuredWorkout:
    days = [
        WorkoutDay(
            name=f"Day {i + 1}",
            focus="full body",
            exercises=[WorkoutExercise(name="Squat", sets=3, reps="5")],
        )
        for i in range(day_count)
    ]
    return StructuredWorkout(
        split=f"{day_count}-day",
        goal="fat_loss",
        days=days,
        weekly_sets=3 * day_count,
    )


def _stub_extraction(
    *,
    parseable: bool = True,
    day_count: int = 3,
    findings: list[str] | None = None,
) -> SubmittedPlanExtraction:
    return SubmittedPlanExtraction(
        parseable=parseable,
        workout=_workout(day_count) if parseable else None,
        findings=findings or [],
    )


# --- Unit tests: normalize_submitted_plan --------------------------------------------


def test_normalize_well_formed_plan_matches_profile_day_count() -> None:
    configure_submitted_plan_extractor(lambda _text: _stub_extraction(day_count=3))
    result = normalize_submitted_plan(
        "Day 1: Squat 3x5\nDay 2: ...\nDay 3: ...", {"days_per_week": 3}
    )
    assert result["structured_workout"] is not None
    assert len(result["structured_workout"]["days"]) == 3
    assert result["normalization_findings"] == []
    configure_submitted_plan_extractor(None)


def test_normalize_day_count_conflict_preserves_submitted_shape_and_records_finding() -> None:
    """Design review F7 / design-doc Sec5.4: never coerce to the profile's day count."""
    configure_submitted_plan_extractor(lambda _text: _stub_extraction(day_count=5))
    result = normalize_submitted_plan("5-day plan text", {"days_per_week": 3})
    assert result["structured_workout"] is not None
    assert len(result["structured_workout"]["days"]) == 5  # submitted shape preserved
    assert any("day_count_mismatch" in finding for finding in result["normalization_findings"])
    configure_submitted_plan_extractor(None)


def test_normalize_unparseable_plan_returns_none_with_finding() -> None:
    configure_submitted_plan_extractor(lambda _text: _stub_extraction(parseable=False))
    result = normalize_submitted_plan("complete gibberish, no workout here", {"days_per_week": 3})
    assert result["structured_workout"] is None
    assert any("unparseable" in finding for finding in result["normalization_findings"])
    configure_submitted_plan_extractor(None)


def test_normalize_carries_forward_extractor_findings() -> None:
    configure_submitted_plan_extractor(
        lambda _text: _stub_extraction(
            day_count=3, findings=["stated_macros: 2500 kcal mentioned in text"]
        )
    )
    result = normalize_submitted_plan("plan text", {"days_per_week": 3})
    assert "stated_macros: 2500 kcal mentioned in text" in result["normalization_findings"]
    configure_submitted_plan_extractor(None)


# --- Routing unit tests ----------------------------------------------------------------


def test_route_after_macros_evaluate_mode() -> None:
    assert _route_after_macros({"fitness_mode": "evaluate"}) == "normalize_submitted_plan"  # type: ignore[arg-type]


def test_route_after_macros_generate_mode_unaffected() -> None:
    assert _route_after_macros({"fitness_mode": None}) == "resolve_workout_template"  # type: ignore[arg-type]
    assert _route_after_macros({"fitness_mode": "generate"}) == "resolve_workout_template"  # type: ignore[arg-type]


def test_route_after_safety_evaluate_mode_never_retries() -> None:
    """Correction to the original Phase 4 spec, documented in graph.py: evaluate mode has
    no LLM-generation retry loop -- a failed safety check must go straight to
    synthesize_plan, never to fitness_planner."""
    failing_state = {
        "fitness_mode": "evaluate",
        "safety_result": {"passed": False, "feedback": ["x"]},
        "planner_attempts": 0,
        "max_planner_attempts": 2,
    }
    assert _route_after_safety(failing_state) == "synthesize_plan"  # type: ignore[arg-type]


def test_route_after_safety_generate_mode_still_retries() -> None:
    failing_state = {
        "fitness_mode": None,
        "safety_result": {"passed": False, "feedback": ["x"]},
        "planner_attempts": 0,
        "max_planner_attempts": 2,
    }
    assert _route_after_safety(failing_state) == "fitness_planner"  # type: ignore[arg-type]


# --- Integration: full evaluate-mode Fitness subgraph run ------------------------------


@pytest.fixture
def evaluate_orchestration_state(tmp_path: Path, complete_profile: dict[str, Any]) -> dict:
    state = create_initial_state(
        run_id="evaluate-run",
        thread_id="evaluate-thread",
        query="check my plan",
        user_profile=complete_profile,
        workspace_root=tmp_path / "workspace",
        submitted_plan_text="Day 1: Squat 3x5\nDay 2: Bench 3x5\nDay 3: Deadlift 3x5",
    )
    seed_execution_plan(state["workspace_path"], complete_profile)
    return {
        **state,
        "execution_plan": {
            "user_intent": "verify",
            "workflow": "VerifyExternalWorkflow",
            "ordered_domains": ["fitness", "verify"],
            "fitness_mode": "evaluate",
            "verification_strategy": "EXTERNAL_PLAN",
        },
    }


def test_evaluate_mode_full_subgraph_run_produces_structured_workout(
    evaluate_orchestration_state: dict,
) -> None:
    configure_submitted_plan_extractor(lambda _text: _stub_extraction(day_count=3))
    fitness_state = to_fitness_state(evaluate_orchestration_state)  # type: ignore[arg-type]
    assert fitness_state["fitness_mode"] == "evaluate"

    result = build_fitness_subgraph().invoke(fitness_state)

    assert result["structured_workout"] is not None
    assert len(result["structured_workout"]["days"]) == 3
    assert result["draft_plan"] is not None

    vfs = VFS.for_run(Path(evaluate_orchestration_state["workspace_path"]))
    assert vfs.exists("fitness/workout.json")
    assert vfs.exists("fitness/final_plan.md")
    assert vfs.exists("fitness/normalization_findings.json")
    configure_submitted_plan_extractor(None)


def test_evaluate_mode_malformed_plan_writes_no_workout_artifact(
    evaluate_orchestration_state: dict,
) -> None:
    configure_submitted_plan_extractor(lambda _text: _stub_extraction(parseable=False))
    fitness_state = to_fitness_state(evaluate_orchestration_state)  # type: ignore[arg-type]

    result = build_fitness_subgraph().invoke(fitness_state)

    assert result["structured_workout"] is None
    # _write_artifacts_node's existing None guard: nothing written for this run.
    vfs = VFS.for_run(Path(evaluate_orchestration_state["workspace_path"]))
    assert not vfs.exists("fitness/workout.json")
    configure_submitted_plan_extractor(None)


def _unsafe_duplicate_exercise_workout(day_count: int) -> StructuredWorkout:
    """A parseable, well-formed submission whose first day repeats an exercise --
    fails validate_workout_safety_data's duplicate_exercise check without being
    malformed or unparseable."""
    first_day = WorkoutDay(
        name="Day 1",
        focus="full body",
        exercises=[
            WorkoutExercise(name="Squat", sets=3, reps="5"),
            WorkoutExercise(name="Squat", sets=3, reps="5"),
        ],
    )
    other_days = [
        WorkoutDay(
            name=f"Day {i + 1}",
            focus="full body",
            exercises=[WorkoutExercise(name="Squat", sets=3, reps="5")],
        )
        for i in range(1, day_count)
    ]
    days = [first_day, *other_days]
    return StructuredWorkout(
        split=f"{day_count}-day",
        goal="fat_loss",
        days=days,
        weekly_sets=sum(len(day.exercises) for day in days),
    )


def test_evaluate_mode_safety_failure_preserves_structured_workout(
    evaluate_orchestration_state: dict,
) -> None:
    """Regression for the structured_workout-nulled-by-safety_check bug: a parseable but
    unsafe submitted plan must still flow through to synthesize_plan/write_artifacts as
    itself, with safety_result.passed False -- not be silently discarded because
    _safety_check_node's generate/edit-mode retry-reset used to fire unconditionally,
    even though evaluate mode's _route_after_safety never loops back to fitness_planner
    to regenerate it."""
    configure_submitted_plan_extractor(
        lambda _text: SubmittedPlanExtraction(
            parseable=True,
            workout=_unsafe_duplicate_exercise_workout(3),
            findings=[],
        )
    )
    fitness_state = to_fitness_state(evaluate_orchestration_state)  # type: ignore[arg-type]

    result = build_fitness_subgraph().invoke(fitness_state)

    assert result["safety_result"]["passed"] is False
    assert result["structured_workout"] is not None
    assert len(result["structured_workout"]["days"]) == 3
    assert result["draft_plan"] is not None
    assert "Workout plan unavailable" not in result["draft_plan"]

    vfs = VFS.for_run(Path(evaluate_orchestration_state["workspace_path"]))
    assert vfs.exists("fitness/final_plan.md")
    assert vfs.exists("fitness/workout.json")
    configure_submitted_plan_extractor(None)


def test_to_fitness_state_generate_mode_unaffected_by_new_fields(
    tmp_path: Path, complete_profile: dict[str, Any]
) -> None:
    """Regression: a plain generate run (no execution_plan) still gets fitness_mode=None
    and an empty submitted_plan_text, never breaking generate/edit's existing inference."""
    state = create_initial_state(
        run_id="generate-run",
        thread_id="generate-thread",
        query="build me a plan",
        user_profile=complete_profile,
        workspace_root=tmp_path / "workspace",
    )
    fitness_state = to_fitness_state(state)
    assert fitness_state["fitness_mode"] is None
    assert fitness_state["submitted_plan_text"] is None
    assert fitness_state["normalization_findings"] == []
