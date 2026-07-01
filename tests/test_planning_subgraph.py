import json
from pathlib import Path
from typing import Any

import pytest

from core.agents.state import OrchestrationState
from core.graph.run import create_initial_state
from core.profile.extraction import configure_profile_extractor
from core.profile.schema import Constraints, ExtractedProfile, Goal, Profile
from core.subgraphs.planning.agent import PlanningAgent
from core.subgraphs.planning.graph import build_planning_subgraph, invoke_planning_subgraph
from core.subgraphs.planning.planning_agent import configure_planning_agent
from core.subgraphs.planning.schema import ExecutionPlan, PlanTask
from core.subgraphs.planning.state import PlanningState
from core.subgraphs.planning.tools import extract_profile, generate_plan, validate_profile
from core.subgraphs.planning.utils import (
    build_profile,
    has_execution_plan,
    has_planning_todos,
    validate_profile_data,
)
from core.vfs import VFS


@pytest.fixture
def workspace_root(tmp_path: Path) -> Path:
    return tmp_path / "workspace"


@pytest.fixture
def complete_profile() -> dict:
    return {
        "age": 30,
        "sex": "male",
        "height_cm": 175,
        "current_weight_kg": 85.0,
        "target_weight_kg": 75.0,
        "activity_level": "gym_3x_week",
        "goal": "fat_loss",
    }


def _mock_fat_loss_execution_plan(**_kwargs: Any) -> ExecutionPlan:
    return ExecutionPlan(
        plan_rationale=(
            "Fat loss research plan for a 3x/week gym user targeting 75 kg with "
            "evidence-based training and nutrition retrieval."
        ),
        tasks=[
            PlanTask(
                order=1,
                task="Research caloric deficit strategies for fat loss at gym_3x_week",
                rationale="Tailor energy balance evidence to the user's fat_loss goal.",
            ),
            PlanTask(
                order=2,
                task="Gather hypertrophy-preserving training volume during fat loss",
                rationale="Protect lean mass while cutting for this activity level.",
            ),
            PlanTask(
                order=3,
                task="Collect protein and recovery guidance for 85 kg male cutting phase",
                rationale="Align macro and recovery evidence with user biometrics.",
            ),
        ],
        plan_markdown=(
            "# Fat Loss Planning Summary\n\n"
            "- Goal: fat_loss\n"
            "- Activity: gym_3x_week\n"
            "- Tasks: 3 tailored research steps\n"
        ),
    )


@pytest.fixture
def planning_state(workspace_root: Path, complete_profile: dict) -> PlanningState:
    initial = create_initial_state(
        run_id="plan-run",
        thread_id="plan-thread",
        query="I want to lose weight with a gym 3x/week plan.",
        user_profile=complete_profile,
        workspace_root=workspace_root,
    )
    return PlanningState(
        query=initial["query"],
        user_profile=initial["user_profile"],
        constraints=initial["constraints"],
        request_type="fat_loss",
        workspace_path=initial["workspace_path"],
        profile={},
        missing_fields=[],
        todos=[],
        execution_plan={},
        planning_output=None,
        requires_hitl=False,
    )


def test_extract_profile_merges_query_and_profile(complete_profile: dict) -> None:
    configure_profile_extractor(
        lambda _query: ExtractedProfile(
            profile=Profile(
                sex="male",
                age=30,
                height_cm=175,
                current_weight_kg=85,
            ),
            goal=Goal(goal="fat_loss", target_weight_kg=75),
            constraints=Constraints(days_per_week=3),
        )
    )
    query = "I want to lose weight. Male, 30 years old, 175 cm, 85 kg. Gym 3x/week. Goal: 75 kg"
    result = extract_profile.invoke(
        {
            "query": query,
            "user_profile": {},
            "constraints": {"days_per_week": 3},
        }
    )
    profile = result["profile"]
    assert profile["sex"] == "male"
    assert profile["age"] == 30
    assert profile["height_cm"] == 175
    assert profile["current_weight_kg"] == 85.0
    assert profile["target_weight_kg"] == 75.0
    assert profile["activity_level"] == "gym_3x_week"
    assert profile["goal"] == "fat_loss"
    assert profile["days_per_week"] == 3
    assert "lose weight" in profile["query"]


def test_extract_profile_prefers_existing_user_profile(complete_profile: dict) -> None:
    configure_profile_extractor(
        lambda _query: (_ for _ in ()).throw(AssertionError("extractor should be skipped"))
    )
    result = extract_profile.invoke(
        {
            "query": "Male, 40 years old, 180 cm, 90 kg",
            "user_profile": complete_profile,
            "constraints": {},
        }
    )
    profile = result["profile"]
    assert profile["age"] == 30
    assert profile["height_cm"] == 175


def test_extract_profile_parses_natural_language_query() -> None:
    configure_profile_extractor(
        lambda _query: ExtractedProfile(
            profile=Profile(age=27, height_cm=171, current_weight_kg=75),
            goal=Goal(goal="fat_loss", target_weight_kg=73),
        )
    )
    query = "im 27, 75kg, 171cm, i want to lose 2kg in 2 months"
    result = extract_profile.invoke(
        {
            "query": query,
            "user_profile": {},
            "constraints": {},
        }
    )
    profile = result["profile"]
    assert profile["age"] == 27
    assert profile["height_cm"] == 171
    assert profile["current_weight_kg"] == 75.0
    assert profile["target_weight_kg"] == 73.0
    assert profile["goal"] == "fat_loss"


def test_extract_profile_parses_muscle_gain_query() -> None:
    configure_profile_extractor(
        lambda _query: ExtractedProfile(
            profile=Profile(age=27, height_cm=171, current_weight_kg=73),
            goal=Goal(goal="muscle_gain", target_weight_kg=75),
            constraints=Constraints(days_per_week=5),
        )
    )
    query = (
        "i want to gain 2 kg muscle, height 171cm, weight 73kg, age 27, training 5 days per week"
    )
    result = extract_profile.invoke(
        {
            "query": query,
            "user_profile": {},
            "constraints": {"days_per_week": 4, "equipment": "gym"},
        }
    )
    profile = result["profile"]
    assert profile["age"] == 27
    assert profile["height_cm"] == 171
    assert profile["current_weight_kg"] == 73.0
    assert profile["target_weight_kg"] == 75.0
    assert profile["goal"] == "muscle_gain"
    assert profile["activity_level"] == "gym_5x_week"
    assert profile["days_per_week"] == 5


def test_build_profile_skips_extraction_when_profile_complete(complete_profile: dict) -> None:
    configure_profile_extractor(
        lambda _query: (_ for _ in ()).throw(AssertionError("extractor should be skipped"))
    )
    profile = build_profile(
        query="I want to lose weight with a gym 3x/week plan.",
        user_profile=complete_profile,
        constraints={},
    )
    assert validate_profile_data(profile)["requires_hitl"] is False
    assert profile["age"] == 30
    assert profile["goal"] == "fat_loss"


def test_validate_profile_flags_missing_fields() -> None:
    result = validate_profile.invoke({"profile": {"goal": "fat_loss"}})
    assert "age" in result["missing_fields"]
    assert "target_weight_kg" in result["missing_fields"]
    assert result["requires_hitl"] is True


def test_validate_profile_passes_complete_profile(complete_profile: dict) -> None:
    result = validate_profile.invoke({"profile": complete_profile})
    assert result["missing_fields"] == []
    assert result["requires_hitl"] is False


def test_generate_plan_persists_vfs_artifacts(planning_state: PlanningState) -> None:
    configure_planning_agent(_mock_fat_loss_execution_plan)
    result = generate_plan.invoke(
        {
            "profile": planning_state["user_profile"],
            "query": planning_state["query"],
            "request_type": planning_state["request_type"],
            "constraints": planning_state["constraints"],
            "workspace_path": planning_state["workspace_path"],
        }
    )
    vfs = VFS.for_run(Path(planning_state["workspace_path"]))
    assert len(result["todos"]) == 3
    assert "fat loss" in result["todos"][0].lower()
    assert vfs.exists("plan/execution_plan.json")
    assert vfs.exists("plan/todos.json")
    assert vfs.exists("plan/profile.json")
    assert vfs.exists("plan/plan.md")
    assert vfs.read("plan/plan.md") == result["planning_output"]
    execution_plan = json.loads(vfs.read("plan/execution_plan.json"))
    assert execution_plan["plan_rationale"]
    assert len(execution_plan["tasks"]) == 3
    todos = json.loads(vfs.read("plan/todos.json"))
    assert todos == result["todos"]


def test_planning_subgraph_writes_execution_plan_on_complete_profile(
    planning_state: PlanningState,
) -> None:
    configure_profile_extractor(lambda _query: ExtractedProfile())
    configure_planning_agent(_mock_fat_loss_execution_plan)
    graph = build_planning_subgraph()
    graph.invoke(planning_state)
    assert has_execution_plan(planning_state["workspace_path"]) is True
    assert has_planning_todos(planning_state["workspace_path"]) is True


def test_planning_subgraph_missing_fields_sets_hitl_flag(workspace_root: Path) -> None:
    configure_profile_extractor(lambda _query: ExtractedProfile(goal=Goal(goal="fat_loss")))
    initial = create_initial_state(
        run_id="plan-hitl",
        thread_id="plan-hitl-thread",
        query="I want to lose weight.",
        workspace_root=workspace_root,
    )
    orchestration_state: OrchestrationState = {
        **initial,
        "request_type": "fat_loss",
        "affected_domains": ["planning", "research", "fitness", "verify"],
    }
    updates = invoke_planning_subgraph(orchestration_state)
    assert updates["waiting_for_user"] is True
    assert has_execution_plan(initial["workspace_path"]) is False


def test_planning_agent_runs_from_orchestration(planning_state: PlanningState) -> None:
    configure_profile_extractor(lambda _query: ExtractedProfile())
    configure_planning_agent(_mock_fat_loss_execution_plan)
    orchestration_state: OrchestrationState = {
        "run_id": "plan-run",
        "thread_id": "plan-thread",
        "current_node": "supervisor",
        "query": planning_state["query"],
        "user_profile": planning_state["user_profile"],
        "constraints": planning_state["constraints"],
        "request_type": planning_state["request_type"],
        "affected_domains": ["planning", "research", "fitness", "verify"],
        "route_decision": None,
        "retry_count": 0,
        "replan_count": 0,
        "verification_passed": False,
        "faithfulness_score": None,
        "waiting_for_user": False,
        "approval_status": None,
        "user_response": None,
        "workspace_path": planning_state["workspace_path"],
        "final_artifact_path": None,
    }
    agent = PlanningAgent()
    updates = agent.run(orchestration_state)
    assert updates["current_node"] == "planning"
    assert has_execution_plan(planning_state["workspace_path"]) is True
