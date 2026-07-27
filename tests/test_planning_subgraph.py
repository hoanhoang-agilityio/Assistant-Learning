import json
from pathlib import Path
from typing import Any

import pytest

from core.agents.state import OrchestrationState
from core.profile.extraction import configure_profile_extractor
from core.profile.goal_spec import derive_goal_spec
from core.profile.schema import ExtractedProfile
from core.profile.store import load_run_profile, persist_profile
from core.subgraphs.planning.agent import PlanningAgent
from core.subgraphs.planning.graph import (
    build_planning_subgraph,
    generate_plan,
    invoke_planning_subgraph,
)
from core.subgraphs.planning.planning_agent import configure_planning_agent
from core.subgraphs.planning.schema import ExecutionPlan, PlanTask
from core.subgraphs.planning.state import PlanningState
from core.subgraphs.planning.utils import (
    build_planning_payload,
    compact_profile_for_llm,
    has_execution_plan,
    has_planning_todos,
    load_planning_todos,
    persist_execution_plan,
    persist_revision_feedback,
    should_reuse_execution_plan,
)
from core.subgraphs.user.utils import extract_profile
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
    """Planning always trusts an already-complete, already-validated raw profile on VFS.

    Completion/validation is normally performed by the User subgraph before Planning ever
    runs -- simulate that here via ``extract_profile`` directly (skips the LLM since
    ``complete_profile`` is already complete/feasible), then persist it to
    `plan/profile.json` the same way the User subgraph's `_persist_node` does. Planning
    derives `GoalSpec` fresh from this raw profile itself (never from a cached/enriched
    copy) rather than from an embedded `PlanningState` field, so the fixture must seed
    that file itself.
    """
    query = "I want to lose weight with a gym 3x/week plan."
    workspace_path = str(workspace_root / "runs" / "plan-run")
    normalized_profile = extract_profile(query=query, profile=complete_profile)
    persist_profile(workspace_path, normalized_profile)
    return PlanningState(
        query=query,
        request_type="fat_loss",
        workspace_path=workspace_path,
        route_decision=None,
        revision_feedback=None,
        reused_execution_plan=False,
    )


def test_compact_profile_for_llm_strips_query_and_metadata() -> None:
    profile = {
        "query": "I want to lose weight with a gym 3x/week plan.",
        "missing_fields": ["sex"],
        "age": 30,
        "goal": "fat_loss",
        "days_per_week": 3,
        "activity_level": "gym_3x_week",
    }
    compact = compact_profile_for_llm(profile)
    assert "query" not in compact
    assert "missing_fields" not in compact
    assert compact["age"] == 30
    assert compact["goal"] == "fat_loss"
    assert compact["days_per_week"] == 3


def test_build_planning_payload_deduplicates_constraints(complete_profile: dict) -> None:
    profile = {
        **complete_profile,
        "query": "I want to lose weight with a gym 3x/week plan.",
        "days_per_week": 3,
        "equipment": "gym",
    }
    constraints = {"days_per_week": 3, "equipment": "gym", "high_protein": True}
    payload = build_planning_payload(
        profile=profile,
        goal_spec=derive_goal_spec(profile),
        query=profile["query"],
        request_type="fat_loss",
        constraints=constraints,
    )
    assert payload["profile"]["goal"] == "fat_loss"
    assert "query" not in payload["profile"]
    assert payload["constraints"] == {"high_protein": True}


def test_generate_plan_persists_vfs_artifacts(planning_state: PlanningState) -> None:
    configure_planning_agent(_mock_fat_loss_execution_plan)
    result = generate_plan(
        profile=load_run_profile(planning_state["workspace_path"]),
        query=planning_state["query"],
        request_type=planning_state["request_type"],
        workspace_path=planning_state["workspace_path"],
    )
    vfs = VFS.for_run(Path(planning_state["workspace_path"]))
    todos = load_planning_todos(planning_state["workspace_path"])
    assert len(todos) == 3
    assert "fat loss" in todos[0].lower()
    assert vfs.exists("plan/execution_plan.json")
    assert vfs.exists("plan/profile.json")
    assert vfs.exists("plan/plan.md")
    assert result == {}
    execution_plan = json.loads(vfs.read("plan/execution_plan.json"))
    assert execution_plan["plan_rationale"]
    assert len(execution_plan["tasks"]) == 3
    assert vfs.read("plan/plan.md") == execution_plan["plan_markdown"]


def test_planning_subgraph_writes_execution_plan_on_complete_profile(
    planning_state: PlanningState,
) -> None:
    configure_planning_agent(_mock_fat_loss_execution_plan)
    graph = build_planning_subgraph()
    graph.invoke(planning_state)
    assert has_execution_plan(planning_state["workspace_path"]) is True
    assert has_planning_todos(planning_state["workspace_path"]) is True


def _plan_without_macro_keywords() -> ExecutionPlan:
    return ExecutionPlan(
        plan_rationale="Generic training research plan without nutrition focus.",
        tasks=[
            PlanTask(
                order=1,
                task="Research general strength training principles",
                rationale="Foundational strength evidence for the user goal.",
            ),
            PlanTask(
                order=2,
                task="Gather recovery guidance for active individuals",
                rationale="Support recovery decisions with credible sources.",
            ),
            PlanTask(
                order=3,
                task="Verify fitness-domain credibility of selected sources",
                rationale="Ensure downstream synthesis relies on trustworthy evidence.",
            ),
        ],
        plan_markdown=(
            "# Training Summary\n\n- Tasks: 3 research-oriented steps without macro focus\n"
        ),
    )


def _seed_replan_workspace(
    workspace_path: str,
    profile: dict[str, Any],
    plan: ExecutionPlan,
    *,
    issues: list[str],
) -> None:
    Path(workspace_path).mkdir(parents=True, exist_ok=True)
    persist_execution_plan(profile, plan, workspace_path)
    vfs = VFS.for_run(Path(workspace_path))
    vfs.write(
        "verify/verification_v1.json",
        json.dumps(
            {
                "passed": False,
                "consistency": {"passed": False, "issues": issues},
            }
        ),
    )


def test_replan_reuses_execution_plan_when_profile_and_coverage_match(
    planning_state: PlanningState,
) -> None:
    configure_profile_extractor(lambda _query: ExtractedProfile())
    configure_planning_agent(
        lambda **_kwargs: (_ for _ in ()).throw(AssertionError("generate_plan should be skipped"))
    )
    _seed_replan_workspace(
        planning_state["workspace_path"],
        load_run_profile(planning_state["workspace_path"]),
        _mock_fat_loss_execution_plan(),
        issues=["missing_macro_targets"],
    )
    state = {
        **planning_state,
        "route_decision": "REPLAN",
    }
    result = build_planning_subgraph().invoke(state)
    assert result["reused_execution_plan"] is True
    assert len(load_planning_todos(planning_state["workspace_path"])) == 3


def test_replan_regenerates_when_plan_lacks_issue_coverage(
    planning_state: PlanningState,
) -> None:
    configure_profile_extractor(lambda _query: ExtractedProfile())
    configure_planning_agent(_mock_fat_loss_execution_plan)
    _seed_replan_workspace(
        planning_state["workspace_path"],
        load_run_profile(planning_state["workspace_path"]),
        _plan_without_macro_keywords(),
        issues=["missing_macro_targets"],
    )
    state = {
        **planning_state,
        "route_decision": "REPLAN",
    }
    result = build_planning_subgraph().invoke(state)
    assert result.get("reused_execution_plan") is not True
    assert len(load_planning_todos(planning_state["workspace_path"])) == 3


def test_replan_regenerates_when_profile_changed(
    planning_state: PlanningState,
    complete_profile: dict,
) -> None:
    """`should_reuse_execution_plan` must detect a profile mismatch and force
    regeneration. Exercised as a direct unit call rather than through the compiled
    subgraph: Planning now loads its "current" profile from the same VFS file
    `profile_matches_stored_profile` compares against, so a graph-level invoke can no
    longer represent "current profile differs from the stored one" as two distinct
    values -- both reads would hit the identical `plan/profile.json`.
    """
    configure_profile_extractor(lambda _query: ExtractedProfile())
    stored_profile = extract_profile(
        query=planning_state["query"],
        profile=complete_profile,
    )
    _seed_replan_workspace(
        planning_state["workspace_path"],
        stored_profile,
        _mock_fat_loss_execution_plan(),
        issues=["missing_macro_targets"],
    )
    changed_profile = extract_profile(
        query=planning_state["query"],
        profile={**complete_profile, "age": 25},
    )
    assert (
        should_reuse_execution_plan("REPLAN", planning_state["workspace_path"], changed_profile)
        is False
    )


def test_first_run_always_generates_plan(planning_state: PlanningState) -> None:
    configure_planning_agent(_mock_fat_loss_execution_plan)
    result = build_planning_subgraph().invoke(planning_state)
    assert result.get("reused_execution_plan") is not True


def test_planning_agent_runs_from_orchestration(planning_state: PlanningState) -> None:
    configure_planning_agent(_mock_fat_loss_execution_plan)
    orchestration_state: OrchestrationState = {
        "run_id": "plan-run",
        "thread_id": "plan-thread",
        "current_node": "supervisor",
        "query": planning_state["query"],
        "fitness_query": planning_state["query"],
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


def test_replan_skips_reuse_when_revision_feedback_present(
    planning_state: PlanningState,
) -> None:
    configure_profile_extractor(lambda _query: ExtractedProfile())
    configure_planning_agent(_mock_fat_loss_execution_plan)
    _seed_replan_workspace(
        planning_state["workspace_path"],
        load_run_profile(planning_state["workspace_path"]),
        _mock_fat_loss_execution_plan(),
        issues=["missing_macro_targets"],
    )
    persist_revision_feedback(
        planning_state["workspace_path"],
        "User wants fewer training days.",
    )
    state = {
        **planning_state,
        "route_decision": "REPLAN",
    }
    result = build_planning_subgraph().invoke(state)
    assert result.get("reused_execution_plan") is not True


def test_invoke_planning_subgraph_does_not_touch_user_profile(
    planning_state: PlanningState,
) -> None:
    """`OrchestrationState` no longer has `user_profile`/`constraints` fields at all, so
    `invoke_planning_subgraph`'s update dict structurally cannot contain them -- this is
    now a guard against either field being reintroduced later.
    """
    configure_planning_agent(_mock_fat_loss_execution_plan)
    orchestration_state: OrchestrationState = {
        "run_id": "plan-run-2",
        "thread_id": "plan-thread-2",
        "current_node": "supervisor",
        "query": planning_state["query"],
        "fitness_query": planning_state["query"],
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
    updates = invoke_planning_subgraph(orchestration_state)
    assert "user_profile" not in updates
    assert "constraints" not in updates
    assert updates["current_node"] == "planning"
