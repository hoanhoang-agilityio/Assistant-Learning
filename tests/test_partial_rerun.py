import json
from pathlib import Path

import pytest

from core.agents.rerun import MAX_REPLAN_COUNT, MAX_RETRY_COUNT, partial_rerun_decision_data
from core.agents.state import OrchestrationState
from core.agents.supervisor import supervisor_node
from core.agents.tools import hitl_control, partial_rerun_decision
from core.graph.routing import route_from_supervisor
from core.graph.run import create_initial_state
from core.vfs import VFS


def _failed_report(
    *,
    consistency_issues: list[str] | None = None,
    citation_issues: list[str] | None = None,
    ragas_pass: bool = True,
    safety_issues: list[str] | None = None,
) -> dict:
    return {
        "passed": False,
        "citation": {"passed": not citation_issues, "issues": citation_issues or []},
        "consistency": {"passed": not consistency_issues, "issues": consistency_issues or []},
        "safety": {"passed": not safety_issues, "issues": safety_issues or []},
        "ragas": {"pass_fail": ragas_pass, "faithfulness_score": 0.5},
        "feedback": "verification failed",
    }


def test_partial_rerun_replan_for_structural_issues() -> None:
    report = _failed_report(consistency_issues=["missing_macro_targets"])
    result = partial_rerun_decision.invoke(
        {"verification_report": report, "retry_count": 0, "replan_count": 0}
    )
    assert result["route_decision"] == "REPLAN"
    assert result["replan_count"] == 1


def test_partial_rerun_reresearch_for_evidence_issues() -> None:
    report = _failed_report(citation_issues=["no_sources_referenced_in_draft"])
    result = partial_rerun_decision.invoke(
        {"verification_report": report, "retry_count": 0, "replan_count": 0}
    )
    assert result["route_decision"] == "RERESEARCH"
    assert result["retry_count"] == 1


def test_partial_rerun_fix_reasoning_for_minor_issues() -> None:
    report = _failed_report(safety_issues=["aggressive_calorie_deficit"])
    result = partial_rerun_decision.invoke(
        {"verification_report": report, "retry_count": 0, "replan_count": 0}
    )
    assert result["route_decision"] == "FIX_REASONING"
    assert result["retry_count"] == 1


def test_partial_rerun_hitl_when_retries_exhausted() -> None:
    report = _failed_report(safety_issues=["aggressive_calorie_deficit"])
    result = partial_rerun_decision_data(report, MAX_RETRY_COUNT, 0)
    assert result["route_decision"] == "HITL"
    assert result["waiting_for_user"] is True


def test_partial_rerun_hitl_when_replan_exhausted() -> None:
    report = _failed_report(consistency_issues=["missing_macro_targets"])
    result = partial_rerun_decision_data(report, 0, MAX_REPLAN_COUNT)
    assert result["route_decision"] == "HITL"


def test_route_from_supervisor_rerun_targets() -> None:
    base = create_initial_state(
        run_id="rerun-run",
        thread_id="rerun-thread",
        query="test",
        workspace_root=Path("/tmp/rerun-workspace"),
    )
    fix_state: OrchestrationState = {**base, "route_decision": "FIX_REASONING", "retry_count": 1}
    assert route_from_supervisor(fix_state) == "fitness"

    replan_state: OrchestrationState = {
        **base,
        "route_decision": "REPLAN",
        "replan_count": 1,
        "current_node": "verification",
    }
    assert route_from_supervisor(replan_state) == "planning"

    replan_continue_state: OrchestrationState = {
        **base,
        "route_decision": "REPLAN",
        "replan_count": 1,
        "current_node": "planning",
    }
    assert route_from_supervisor(replan_continue_state) == "research"

    research_state: OrchestrationState = {
        **base,
        "route_decision": "RERESEARCH",
        "retry_count": 1,
        "current_node": "verification",
    }
    assert route_from_supervisor(research_state) == "research"

    reresearch_continue_state: OrchestrationState = {
        **base,
        "route_decision": "RERESEARCH",
        "retry_count": 1,
        "current_node": "research",
    }
    assert route_from_supervisor(reresearch_continue_state) == "fitness"


def test_route_from_supervisor_replan_continues_to_fitness_after_research() -> None:
    base = create_initial_state(
        run_id="rerun-run",
        thread_id="rerun-thread",
        query="test",
        workspace_root=Path("/tmp/rerun-workspace"),
    )
    state: OrchestrationState = {
        **base,
        "route_decision": "REPLAN",
        "replan_count": 1,
        "current_node": "research",
    }
    assert route_from_supervisor(state) == "fitness"


def test_route_guards_force_hitl_when_limits_exceeded() -> None:
    base = create_initial_state(
        run_id="guard-run",
        thread_id="guard-thread",
        query="test",
        workspace_root=Path("/tmp/guard-workspace"),
    )
    fix_state: OrchestrationState = {
        **base,
        "route_decision": "FIX_REASONING",
        "retry_count": MAX_RETRY_COUNT,
    }
    assert route_from_supervisor(fix_state) == "hitl"

    replan_state: OrchestrationState = {
        **base,
        "route_decision": "REPLAN",
        "replan_count": MAX_REPLAN_COUNT + 1,
    }
    assert route_from_supervisor(replan_state) == "hitl"


def test_route_from_supervisor_persists_after_hitl_approval() -> None:
    base = create_initial_state(
        run_id="approved-run",
        thread_id="approved-thread",
        query="test",
        workspace_root=Path("/tmp/approved-workspace"),
    )
    hitl_state: OrchestrationState = {
        **base,
        "route_decision": "HITL",
        "approval_status": "approved",
        "waiting_for_user": False,
    }
    assert route_from_supervisor(hitl_state) == "persist"


def test_hitl_control_approve_and_reject() -> None:
    approved = hitl_control.invoke(
        {
            "waiting_for_user": True,
            "approval_status": "pending",
            "user_response": "approve",
        }
    )
    assert approved["approval_status"] == "approved"
    assert approved["waiting_for_user"] is False

    rejected = hitl_control.invoke(
        {
            "waiting_for_user": True,
            "approval_status": "pending",
            "user_response": "reject",
        }
    )
    assert rejected["approval_status"] == "rejected"


@pytest.fixture
def supervisor_state(tmp_path: Path) -> OrchestrationState:
    state = create_initial_state(
        run_id="supervisor-log-run",
        thread_id="supervisor-log-thread",
        query="Build a plan",
        workspace_root=tmp_path / "workspace",
    )
    return {
        **state,
        "request_type": "training_plan",
        "affected_domains": ["planning", "research", "fitness", "verify"],
        "current_node": "verification",
        "verification_passed": False,
    }


def test_supervisor_logs_decision_on_verification_failure(
    supervisor_state: OrchestrationState,
) -> None:
    vfs = VFS.for_run(Path(supervisor_state["workspace_path"]))
    report = _failed_report(safety_issues=["aggressive_calorie_deficit"])
    vfs.write("verify/verification_v1.json", json.dumps(report))

    updates = supervisor_node(supervisor_state)

    assert updates["route_decision"] == "FIX_REASONING"
    assert vfs.exists("logs/supervisor_decisions.jsonl")
    log_line = vfs.read("logs/supervisor_decisions.jsonl").strip()
    entry = json.loads(log_line)
    assert entry["route_decision"] == "FIX_REASONING"
    assert entry["verification_passed"] is False
