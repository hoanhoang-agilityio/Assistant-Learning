import json
from pathlib import Path

import pytest
from langgraph.types import Command

from core.agents.state import OrchestrationState
from core.graph.builder import build_graph
from core.graph.routing import route_from_supervisor
from core.graph.run import create_initial_state
from core.hitl.resume import create_approval_decision, decision_to_resume_update
from core.hitl.tools import request_approval, request_clarification
from core.vfs import VFS


@pytest.fixture
def approval_state(tmp_path: Path) -> OrchestrationState:
    state = create_initial_state(
        run_id="hitl-run",
        thread_id="hitl-thread",
        query="Approve my plan",
        workspace_root=tmp_path / "workspace",
    )
    vfs = VFS.for_run(Path(state["workspace_path"]))
    vfs.write("fitness/final_plan.md", "# Final Plan\n\nMacro targets and training days.")
    vfs.write(
        "verify/verification_v1.json",
        json.dumps({"passed": True, "feedback": None}),
    )
    return {
        **state,
        "request_type": "training_plan",
        "affected_domains": ["planning", "research", "fitness", "verify"],
        "current_node": "supervisor",
        "verification_passed": True,
        "faithfulness_score": 0.95,
        "route_decision": "COMPLETE",
        "waiting_for_user": True,
        "approval_status": "pending",
        # This fixture represents a run already past profile intake/planning/research/
        # fitness/verification, waiting on final approval -- profile was validated earlier.
        "profile_complete": True,
        "profile_valid": True,
    }


def test_request_clarification_sets_waiting_state() -> None:
    result = request_clarification.invoke(
        {
            "missing_fields": ["age", "goal"],
            "context": "Need profile details",
        }
    )
    assert result["waiting_for_user"] is True
    assert result["hitl_type"] == "clarification"
    assert "age" in result["message"]
    assert "fitness goal" in result["message"]


def test_request_approval_sets_waiting_state() -> None:
    result = request_approval.invoke(
        {
            "draft_plan": "# Draft plan content",
            "verification_report": {"passed": True},
        }
    )
    assert result["waiting_for_user"] is True
    assert result["hitl_type"] == "approval"
    assert result["verification_passed"] is True


def test_graph_interrupts_before_hitl_and_resumes_to_persist(
    approval_state: OrchestrationState,
) -> None:
    graph = build_graph()
    config = {"configurable": {"thread_id": approval_state["thread_id"]}}

    paused = graph.invoke(approval_state, config)
    assert paused["waiting_for_user"] is True

    snapshot = graph.get_state(config)
    assert snapshot.next == ("hitl",)

    resumed = graph.invoke(
        Command(
            update={
                "user_response": "approve",
                "approval_status": "approved",
                "waiting_for_user": False,
            }
        ),
        config,
    )
    assert resumed["approval_status"] == "approved"
    assert resumed["current_node"] == "persist"
    assert resumed["final_artifact_path"] is not None


def test_graph_reject_at_approval_ends_without_persist(
    approval_state: OrchestrationState,
) -> None:
    graph = build_graph()
    config = {"configurable": {"thread_id": approval_state["thread_id"]}}

    paused = graph.invoke(approval_state, config)
    assert paused["waiting_for_user"] is True

    resumed = graph.invoke(
        Command(
            update={
                "user_response": "Rejected the plan.",
                "approval_status": "rejected",
                "waiting_for_user": False,
            }
        ),
        config,
    )
    assert resumed["approval_status"] == "rejected"
    assert resumed.get("final_artifact_path") is None
    snapshot = graph.get_state(config)
    assert snapshot.next == ()


def test_graph_interrupts_on_hitl_route_and_resumes_to_persist(
    approval_state: OrchestrationState,
) -> None:
    """When verification fails and route is HITL, approving must still persist."""
    graph = build_graph()
    hitl_state: OrchestrationState = {
        **approval_state,
        "verification_passed": False,
        "route_decision": "HITL",
        "faithfulness_score": 0.5,
    }
    config = {"configurable": {"thread_id": hitl_state["thread_id"]}}

    paused = graph.invoke(hitl_state, config)
    assert paused["waiting_for_user"] is True

    snapshot = graph.get_state(config)
    assert snapshot.next == ("hitl",)

    resumed = graph.invoke(
        Command(
            update={
                "user_response": "approve",
                "approval_status": "approved",
                "waiting_for_user": False,
            }
        ),
        config,
    )
    assert resumed["approval_status"] == "approved"
    assert resumed["current_node"] == "persist"
    assert resumed["final_artifact_path"] is not None

    final_snapshot = graph.get_state(config)
    assert final_snapshot.next == ()


def test_graph_revision_at_approval_routes_to_replan(
    approval_state: OrchestrationState,
) -> None:
    graph = build_graph()
    config = {"configurable": {"thread_id": approval_state["thread_id"]}}

    paused = graph.invoke(approval_state, config)
    assert paused["waiting_for_user"] is True

    update = decision_to_resume_update(
        create_approval_decision(
            "revision",
            message="Reduce training volume and add more recovery days.",
        ),
        replan_count=0,
    )
    merged: OrchestrationState = {
        **paused,
        **update,
        "current_node": "hitl",
        "waiting_for_user": False,
    }
    assert merged["route_decision"] == "REPLAN"
    assert merged.get("replan_count", 0) == 0
    assert merged["revision_feedback"] == "Reduce training volume and add more recovery days."
    assert route_from_supervisor(merged) == "planning"
