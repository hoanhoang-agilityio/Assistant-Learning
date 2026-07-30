"""Unit tests for `invoke_hitl_node` -- the AgentResult-only HITL node (Phase 2
of the hybrid Supervisor routing migration). Never sets `run_complete` or decides
to route to persist itself; the Policy Engine's `_hitl_outcome` rule owns that."""

from pathlib import Path

from core.orchestration.graph.run import create_initial_state
from core.orchestration.hitl.node import invoke_hitl_node


def _pending_state(tmp_path: Path, *, approval_status: str):
    state = create_initial_state(
        run_id="hitl-v2-run",
        thread_id="hitl-v2-thread",
        query="Approve my plan",
        workspace_root=tmp_path,
    )
    state["approval_status"] = approval_status
    state["verification_passed"] = True
    state["waiting_for_user"] = True
    state["user_response"] = "approve" if approval_status == "approved" else "reject"
    return state


def test_approved_reports_agent_result_without_run_complete(tmp_path: Path) -> None:
    state = _pending_state(tmp_path, approval_status="approved")

    updates = invoke_hitl_node(state)

    assert "run_complete" not in updates
    result = updates["last_capability_result"]
    assert result["capability"] == "hitl"
    assert result["status"] == "completed"
    assert result["artifacts"]["approved"] is True
    assert result["next_request"] is None


def test_rejected_reports_agent_result_without_run_complete(tmp_path: Path) -> None:
    state = _pending_state(tmp_path, approval_status="rejected")

    updates = invoke_hitl_node(state)

    assert "run_complete" not in updates
    result = updates["last_capability_result"]
    assert result["capability"] == "hitl"
    assert result["artifacts"]["approved"] is False
