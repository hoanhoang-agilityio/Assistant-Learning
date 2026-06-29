import json
from pathlib import Path

import pytest
from langgraph.types import Command

from core.agents.state import OrchestrationState
from core.graph.builder import build_graph
from core.graph.run import create_initial_state
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
