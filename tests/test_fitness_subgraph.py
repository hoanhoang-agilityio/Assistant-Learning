import json
from pathlib import Path
from typing import Any

import pytest

from core.agents.state import OrchestrationState
from core.graph.run import create_initial_state
from core.subgraphs.fitness.agent import FitnessAgent
from core.subgraphs.fitness.graph import MAX_PLANNER_ATTEMPTS, build_fitness_subgraph
from core.subgraphs.fitness.planner import configure_fitness_planner
from core.subgraphs.fitness.schema import StructuredWorkout, WorkoutDay, WorkoutExercise
from core.subgraphs.fitness.state import FitnessState
from core.subgraphs.fitness.tools import calculate_macros, synthesize_plan
from core.subgraphs.fitness.utils import (
    build_default_structured_workout,
    validate_workout_safety_data,
    write_fitness_artifacts,
)
from core.vfs import VFS
from tests.helpers.fitness import default_structured_workout
from tests.helpers.planning import seed_execution_plan


@pytest.fixture
def workspace_root(tmp_path: Path) -> Path:
    return tmp_path / "workspace"


@pytest.fixture
def complete_profile() -> dict[str, Any]:
    return {
        "age": 30,
        "sex": "male",
        "height_cm": 175,
        "current_weight_kg": 85.0,
        "target_weight_kg": 75.0,
        "activity_level": "gym_3x_week",
        "goal": "fat_loss",
    }


@pytest.fixture
def fitness_state(workspace_root: Path, complete_profile: dict[str, Any]) -> FitnessState:
    initial = create_initial_state(
        run_id="fitness-run",
        thread_id="fitness-thread",
        query="I want to lose weight with strength training.",
        user_profile=complete_profile,
        workspace_root=workspace_root,
    )
    seed_execution_plan(initial["workspace_path"], complete_profile)
    vfs = VFS.for_run(Path(initial["workspace_path"]))
    vfs.write(
        "research/findings.json",
        json.dumps(
            {
                "structured_findings": {
                    "consensus": "10-20 weekly sets per muscle group supports hypertrophy.",
                    "key_findings": ["Use compound lifts for 3-day fat loss plans."],
                    "conflicting_evidence": [],
                    "limitations": [],
                    "recommended_sources": [],
                },
                "evidence_summary": "4 verified hypertrophy sources collected.",
            }
        ),
    )
    return FitnessState(
        workspace_path=initial["workspace_path"],
        profile=complete_profile,
        constraints={"days_per_week": 3, "equipment": "gym"},
        execution_plan={},
        structured_findings=None,
        evidence_summary=None,
        verification_feedback=None,
        macro_targets={},
        training_constraints={},
        structured_workout=None,
        safety_result={"passed": False, "feedback": []},
        planner_feedback=[],
        planner_attempts=0,
        draft_plan=None,
    )


def test_calculate_macros_returns_targets(complete_profile: dict[str, Any]) -> None:
    result = calculate_macros.invoke(
        {
            "profile": complete_profile,
            "constraints": {},
        }
    )
    macros = result["macro_targets"]
    assert macros["calories"] > 0
    assert macros["protein_g"] > 0
    assert macros["carbs_g"] >= 0
    assert macros["fat_g"] > 0
    assert result["training_constraints"]["days_per_week"] == 3


def test_calculate_macros_prefers_profile_training_days_over_constraints() -> None:
    profile = {
        "age": 27,
        "sex": "male",
        "height_cm": 171,
        "current_weight_kg": 73.0,
        "activity_level": "gym_5x_week",
        "goal": "muscle_gain",
        "days_per_week": 5,
    }
    result = calculate_macros.invoke(
        {
            "profile": profile,
            "constraints": {"days_per_week": 4, "equipment": "gym"},
        }
    )
    assert result["training_constraints"]["days_per_week"] == 5
    assert result["macro_targets"]["activity_level"] == "gym_5x_week"


def test_validate_workout_safety_flags_aggressive_deficit(complete_profile: dict[str, Any]) -> None:
    macro_targets = {
        "calories": 900,
        "tdee": 2500,
        "protein_g": 150,
    }
    workout = default_structured_workout(complete_profile, {"days_per_week": 3}).model_dump()
    result = validate_workout_safety_data(
        profile=complete_profile,
        macro_targets=macro_targets,
        training_constraints={"days_per_week": 3, "equipment": "gym", "goal": "fat_loss"},
        structured_workout=workout,
    )
    assert "calories_below_safe_minimum" in result["feedback"]
    assert "aggressive_calorie_deficit" in result["feedback"]
    assert result["passed"] is False


def test_validate_workout_safety_detects_day_count_mismatch(
    complete_profile: dict[str, Any],
) -> None:
    workout = default_structured_workout(complete_profile, {"days_per_week": 4}).model_dump()
    result = validate_workout_safety_data(
        profile=complete_profile,
        macro_targets={"calories": 2200, "tdee": 2500, "protein_g": 150},
        training_constraints={"days_per_week": 3, "equipment": "gym", "goal": "fat_loss"},
        structured_workout=workout,
    )
    assert any("training_day_count_mismatch" in item for item in result["feedback"])


def test_validate_workout_safety_detects_duplicate_exercises(
    complete_profile: dict[str, Any],
) -> None:
    workout = default_structured_workout(complete_profile, {"days_per_week": 3}).model_dump()
    workout["days"][0]["exercises"].append(workout["days"][0]["exercises"][0])
    result = validate_workout_safety_data(
        profile=complete_profile,
        macro_targets={"calories": 2200, "tdee": 2500, "protein_g": 150},
        training_constraints={"days_per_week": 3, "equipment": "gym", "goal": "fat_loss"},
        structured_workout=workout,
    )
    assert any("duplicate_exercise" in item for item in result["feedback"])


def test_validate_workout_safety_detects_bodyweight_equipment_mismatch(
    complete_profile: dict[str, Any],
) -> None:
    workout = StructuredWorkout(
        split="3-day",
        goal="fat_loss",
        days=[
            WorkoutDay(
                name="Day 1",
                focus="full body",
                exercises=[WorkoutExercise(name="Barbell Bench Press", sets=3, reps="8-10")],
            ),
            WorkoutDay(
                name="Day 2",
                focus="full body",
                exercises=[WorkoutExercise(name="Push-up", sets=3, reps="8-12")],
            ),
            WorkoutDay(
                name="Day 3",
                focus="full body",
                exercises=[WorkoutExercise(name="Bodyweight Squat", sets=3, reps="12-15")],
            ),
        ],
        weekly_sets=9,
    ).model_dump()
    result = validate_workout_safety_data(
        profile=complete_profile,
        macro_targets={"calories": 2200, "tdee": 2500, "protein_g": 150},
        training_constraints={"days_per_week": 3, "equipment": "bodyweight", "goal": "fat_loss"},
        structured_workout=workout,
    )
    assert any("equipment_mismatch:bodyweight" in item for item in result["feedback"])


def test_synthesize_plan_includes_macros_and_feedback() -> None:
    macro_targets = {"calories": 2200, "protein_g": 170, "carbs_g": 220, "fat_g": 70}
    structured_workout = build_default_structured_workout(
        {"goal": "fat_loss"},
        {"days_per_week": 1},
    ).model_dump()
    result = synthesize_plan.invoke(
        {
            "macro_targets": macro_targets,
            "structured_workout": structured_workout,
            "evidence_summary": "Evidence summary text",
            "verification_feedback": "Increase weekly volume slightly.",
            "safety_result": {"passed": False, "feedback": ["aggressive_calorie_deficit"]},
        }
    )
    draft_plan = result["draft_plan"]
    assert "Macro Targets" in draft_plan
    assert "Evidence summary text" in draft_plan
    assert "Increase weekly volume slightly." in draft_plan
    assert "aggressive_calorie_deficit" in draft_plan


def test_fitness_subgraph_writes_vfs_artifacts(fitness_state: FitnessState) -> None:
    graph = build_fitness_subgraph()
    graph.invoke(fitness_state)
    vfs = VFS.for_run(Path(fitness_state["workspace_path"]))
    assert vfs.exists("fitness/workout.json")
    assert vfs.exists("fitness/calculations.json")
    assert vfs.exists("fitness/safety_flags.json")
    assert vfs.exists("fitness/final_plan.md")
    calculations = json.loads(vfs.read("fitness/calculations.json"))
    draft_plan = vfs.read("fitness/final_plan.md")
    assert calculations["macro_targets"]["calories"] > 0
    assert calculations["workout_summary"]["sessions"] == 3
    assert "Fitness Plan Draft" in draft_plan


def test_fitness_planner_retries_until_safe(fitness_state: FitnessState) -> None:
    attempts = {"count": 0}

    def flaky_planner(**kwargs: Any) -> StructuredWorkout:
        attempts["count"] += 1
        if attempts["count"] == 1:
            return build_default_structured_workout(
                kwargs["profile"],
                {"days_per_week": 4},
            )
        return default_structured_workout(kwargs["profile"], kwargs["constraints"])

    configure_fitness_planner(flaky_planner)
    graph = build_fitness_subgraph()
    result = graph.invoke(fitness_state)
    assert attempts["count"] == 2
    assert result["safety_result"]["passed"] is True
    assert result["planner_attempts"] == 2


def test_fitness_planner_stops_after_max_attempts(fitness_state: FitnessState) -> None:
    configure_fitness_planner(
        lambda **kwargs: build_default_structured_workout(
            kwargs["profile"],
            {"days_per_week": 4},
        )
    )
    graph = build_fitness_subgraph()
    result = graph.invoke(fitness_state)
    assert result["planner_attempts"] == MAX_PLANNER_ATTEMPTS
    assert result["safety_result"]["passed"] is False
    assert result["draft_plan"]


def test_fitness_agent_runs_from_orchestration(fitness_state: FitnessState) -> None:
    orchestration_state: OrchestrationState = {
        "run_id": "fitness-run",
        "thread_id": "fitness-thread",
        "current_node": "supervisor",
        "query": "lose weight",
        "user_profile": fitness_state["profile"],
        "constraints": fitness_state["constraints"],
        "request_type": "fat_loss",
        "affected_domains": ["planning", "research", "fitness", "verify"],
        "route_decision": None,
        "retry_count": 0,
        "replan_count": 0,
        "verification_passed": False,
        "faithfulness_score": None,
        "waiting_for_user": False,
        "approval_status": None,
        "user_response": None,
        "workspace_path": fitness_state["workspace_path"],
        "final_artifact_path": None,
    }
    agent = FitnessAgent()
    updates = agent.run(orchestration_state)
    assert updates["current_node"] == "fitness"
    vfs = VFS.for_run(Path(fitness_state["workspace_path"]))
    assert vfs.exists("fitness/workout.json")
    assert vfs.exists("fitness/final_plan.md")


def test_write_fitness_artifacts_persists_expected_files(
    fitness_state: FitnessState,
    complete_profile: dict[str, Any],
) -> None:
    macro_result = calculate_macros.invoke({"profile": complete_profile, "constraints": {}})
    structured_workout = default_structured_workout(
        complete_profile,
        {"days_per_week": 3},
    ).model_dump()
    draft = "# Draft"
    write_fitness_artifacts(
        workspace_path=fitness_state["workspace_path"],
        macro_targets=macro_result["macro_targets"],
        structured_workout=structured_workout,
        draft_plan=draft,
        safety_result={"passed": True, "feedback": []},
    )
    vfs = VFS.for_run(Path(fitness_state["workspace_path"]))
    assert vfs.read("fitness/final_plan.md") == draft
    assert vfs.exists("fitness/workout.json")
