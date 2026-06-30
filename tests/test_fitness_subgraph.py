import json
from pathlib import Path
from typing import Any

import pytest

from core.agents.state import OrchestrationState
from core.graph.run import create_initial_state
from core.subgraphs.fitness.agent import FitnessAgent
from core.subgraphs.fitness.graph import build_fitness_subgraph
from core.subgraphs.fitness.state import FitnessState
from core.subgraphs.fitness.tools import calculate_macros, synthesize_plan
from core.subgraphs.fitness.utils import (
    build_training_plan_data,
    detect_safety_flags_data,
    write_fitness_artifacts,
)
from core.subgraphs.planning.utils import write_planning_todos
from core.vfs import VFS


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
    write_planning_todos(complete_profile, "fat_loss", initial["workspace_path"])
    vfs = VFS.for_run(Path(initial["workspace_path"]))
    vfs.write(
        "research/findings.json",
        json.dumps({"evidence_summary": "4 verified hypertrophy sources collected."}),
    )
    return FitnessState(
        workspace_path=initial["workspace_path"],
        profile=complete_profile,
        constraints={"days_per_week": 3, "equipment": "gym"},
        evidence_summary=None,
        verification_feedback=None,
        macro_targets={},
        training_constraints={},
        training_plan=None,
        draft_plan=None,
        safety_flags=[],
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


def test_build_training_plan_creates_sessions(complete_profile: dict[str, Any]) -> None:
    macro_result = calculate_macros.invoke({"profile": complete_profile, "constraints": {}})
    plan_result = build_training_plan_data(
        profile=complete_profile,
        macro_targets=macro_result["macro_targets"],
        training_constraints=macro_result["training_constraints"],
        evidence_summary="verified evidence",
    )
    training_plan = plan_result["training_plan"]
    assert training_plan["split"] == "3-day"
    assert len(training_plan["sessions"]) == 3
    assert training_plan["weekly_sets"] > 0


def test_detect_safety_flags_for_aggressive_deficit(complete_profile: dict[str, Any]) -> None:
    macro_targets = {
        "calories": 900,
        "tdee": 2500,
        "protein_g": 150,
    }
    training_plan = {"sessions": [{}], "weekly_sets": 36}
    result = detect_safety_flags_data(complete_profile, macro_targets, training_plan)
    assert "calories_below_safe_minimum" in result["safety_flags"]
    assert "aggressive_calorie_deficit" in result["safety_flags"]


def test_synthesize_plan_includes_macros_and_feedback() -> None:
    macro_targets = {"calories": 2200, "protein_g": 170, "carbs_g": 220, "fat_g": 70}
    training_plan = {
        "split": "3-day",
        "goal": "fat_loss",
        "sessions": [
            {
                "day": 1,
                "name": "Full Body 1",
                "focus": "fat_loss conditioning",
                "exercises": [{"name": "Squat", "sets": 3, "reps": "6-10"}],
            }
        ],
    }
    result = synthesize_plan.invoke(
        {
            "macro_targets": macro_targets,
            "training_plan": training_plan,
            "evidence_summary": "Evidence summary text",
            "verification_feedback": "Increase weekly volume slightly.",
            "safety_flags": ["aggressive_calorie_deficit"],
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
    assert vfs.exists("fitness/calculations.json")
    assert vfs.exists("fitness/safety_flags.json")
    assert vfs.exists("fitness/final_plan.md")
    calculations = json.loads(vfs.read("fitness/calculations.json"))
    draft_plan = vfs.read("fitness/final_plan.md")
    assert calculations["macro_targets"]["calories"] > 0
    assert "Fitness Plan Draft" in draft_plan


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
    assert vfs.exists("fitness/final_plan.md")


def test_write_fitness_artifacts_persists_expected_files(
    fitness_state: FitnessState,
    complete_profile: dict[str, Any],
) -> None:
    macro_result = calculate_macros.invoke({"profile": complete_profile, "constraints": {}})
    plan_result = build_training_plan_data(
        profile=complete_profile,
        macro_targets=macro_result["macro_targets"],
        training_constraints=macro_result["training_constraints"],
        evidence_summary=None,
    )
    draft = "# Draft"
    write_fitness_artifacts(
        workspace_path=fitness_state["workspace_path"],
        macro_targets=macro_result["macro_targets"],
        training_plan=plan_result["training_plan"],
        draft_plan=draft,
        safety_flags=[],
    )
    vfs = VFS.for_run(Path(fitness_state["workspace_path"]))
    assert vfs.read("fitness/final_plan.md") == draft
