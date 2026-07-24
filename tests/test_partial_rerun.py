import json
from pathlib import Path

import pytest

from core.agents.rerun import MAX_REPLAN_COUNT, MAX_RETRY_COUNT, partial_rerun_decision_data
from core.agents.state import OrchestrationState
from core.agents.supervisor import supervisor_node
from core.graph.routing import route_from_supervisor
from core.graph.run import create_initial_state
from core.hitl.utils import hitl_control_data
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
    result = partial_rerun_decision_data(report, 0, 0)
    assert result["route_decision"] == "REPLAN"
    assert result["replan_count"] == 1


def test_partial_rerun_reresearch_for_evidence_issues() -> None:
    report = _failed_report(citation_issues=["no_sources_referenced_in_draft"])
    result = partial_rerun_decision_data(report, 0, 0)
    assert result["route_decision"] == "RERESEARCH"
    assert result["retry_count"] == 1


def test_partial_rerun_fix_reasoning_for_minor_issues() -> None:
    report = _failed_report(safety_issues=["aggressive_calorie_deficit"])
    result = partial_rerun_decision_data(report, 0, 0)
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


def _external_plan_report(
    *,
    consistency_issues: list[str] | None = None,
    safety_issues: list[str] | None = None,
) -> dict:
    """A report shaped like EXTERNAL_PLAN's actual output -- citation/ragas keys are
    structurally absent, not present-and-failing."""
    return {
        "passed": False,
        "consistency": {"passed": not consistency_issues, "issues": consistency_issues or []},
        "safety": {"passed": not safety_issues, "issues": safety_issues or []},
        "feedback": "verification failed",
    }


def test_partial_rerun_never_emits_reresearch_when_research_absent_from_plan() -> None:
    """Phase 5, design review F4/Sec5.6: a workflow with no research domain (e.g.
    VerifyExternalWorkflow's ["fitness", "verify"]) must never receive a RERESEARCH
    decision -- citation/ragas being absent from the report (not present-and-failing)
    must not be misread as an evidence issue."""
    report = _external_plan_report(safety_issues=["aggressive_calorie_deficit"])
    result = partial_rerun_decision_data(report, 0, 0, ordered_domains=["fitness", "verify"])
    assert result["route_decision"] == "FIX_REASONING"
    assert result["route_decision"] != "RERESEARCH"


def test_partial_rerun_structural_issues_still_replan_without_research() -> None:
    """REPLAN's structural-issue check runs before the has_research gate and is
    unaffected by it."""
    report = _external_plan_report(consistency_issues=["missing_macro_targets"])
    result = partial_rerun_decision_data(report, 0, 0, ordered_domains=["fitness", "verify"])
    assert result["route_decision"] == "REPLAN"


def test_partial_rerun_reresearch_still_reachable_when_research_present() -> None:
    """Backward compatibility: ordered_domains including "research" (or omitted
    entirely, the legacy/None case) preserves today's exact RERESEARCH behavior."""
    report = _failed_report(citation_issues=["no_sources_referenced_in_draft"])
    result = partial_rerun_decision_data(
        report, 0, 0, ordered_domains=["planning", "research", "fitness", "verify"]
    )
    assert result["route_decision"] == "RERESEARCH"


def test_route_from_supervisor_rerun_targets() -> None:
    base = create_initial_state(
        run_id="rerun-run",
        thread_id="rerun-thread",
        query="test",
        workspace_root=Path("/tmp/rerun-workspace"),
    )
    # These assert routing to planning/research/fitness, which the profile guard only
    # allows once the User subgraph has validated the profile -- simulate that here.
    base = {**base, "profile_complete": True, "profile_valid": True}
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
    base = {**base, "profile_complete": True, "profile_valid": True}
    state: OrchestrationState = {
        **base,
        "route_decision": "REPLAN",
        "replan_count": 1,
        "current_node": "research",
    }
    assert route_from_supervisor(state) == "fitness"


def test_route_from_supervisor_replan_reads_execution_plan_entry_domain() -> None:
    """Phase 3: REPLAN's entry-node target comes from RunExecutionPlan.entry_domain when a
    plan is present, not the hardcoded "planning" literal -- a plan whose entry domain is
    "fitness" proves this. FIX_REASONING/RERESEARCH are untouched this phase (out of scope
    per phase_3_technical_spec.md) and must keep targeting their fixed literals regardless
    of execution_plan's presence."""
    base = create_initial_state(
        run_id="rerun-run",
        thread_id="rerun-thread",
        query="test",
        workspace_root=Path("/tmp/rerun-workspace"),
    )
    base = {**base, "profile_complete": True, "profile_valid": True}
    plan = {
        "user_intent": "generate",
        "workflow": "GenerateWorkflow",
        "ordered_domains": ["fitness", "verify"],
        "fitness_mode": "generate",
        "verification_strategy": "FULL",
    }

    replan_state: OrchestrationState = {
        **base,
        "route_decision": "REPLAN",
        "replan_count": 1,
        "current_node": "verification",
        "execution_plan": plan,
    }
    assert route_from_supervisor(replan_state) == "fitness"

    fix_reasoning_state: OrchestrationState = {
        **base,
        "route_decision": "FIX_REASONING",
        "retry_count": 1,
        "execution_plan": plan,
    }
    assert route_from_supervisor(fix_reasoning_state) == "fitness"

    reresearch_state: OrchestrationState = {
        **base,
        "route_decision": "RERESEARCH",
        "retry_count": 1,
        "current_node": "verification",
        "execution_plan": plan,
    }
    assert route_from_supervisor(reresearch_state) == "research"


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


def test_route_from_supervisor_ends_when_plan_rejected() -> None:
    from langgraph.graph import END

    base = create_initial_state(
        run_id="rejected-run",
        thread_id="rejected-thread",
        query="test",
        workspace_root=Path("/tmp/rejected-workspace"),
    )
    rejected_state: OrchestrationState = {
        **base,
        "route_decision": "COMPLETE",
        "approval_status": "rejected",
        "waiting_for_user": False,
    }
    assert route_from_supervisor(rejected_state) == END


def test_route_from_supervisor_replans_after_user_revision() -> None:
    base = create_initial_state(
        run_id="revision-run",
        thread_id="revision-thread",
        query="test",
        workspace_root=Path("/tmp/revision-workspace"),
    )
    # revision_feedback + REPLAN here represents the *result* of the profile guard's
    # redirect through the User subgraph already having happened for this revision --
    # i.e. profile_complete/profile_valid are back to True by the time this fires again.
    base = {**base, "profile_complete": True, "profile_valid": True}
    revision_state: OrchestrationState = {
        **base,
        "current_node": "hitl",
        "route_decision": "REPLAN",
        "replan_count": 1,
        "approval_status": "pending",
        "revision_feedback": "Add more recovery days.",
        "waiting_for_user": False,
    }
    assert route_from_supervisor(revision_state) == "planning"


def test_hitl_control_approve_and_reject() -> None:
    # hitl_control_data called directly -- the @tool wrapper (agents.tools.hitl_control) was
    # removed in the User Subgraph refactor's cleanup pass since it was never bound to an
    # LLM/agent; hitl/node.py already called hitl_control_data directly in production.
    approved = hitl_control_data(
        waiting_for_user=True,
        approval_status="pending",
        user_response="approve",
    )
    assert approved["approval_status"] == "approved"
    assert approved["waiting_for_user"] is False

    rejected = hitl_control_data(
        waiting_for_user=True,
        approval_status="pending",
        user_response="reject",
    )
    assert rejected["approval_status"] == "rejected"

    rejected_message = hitl_control_data(
        waiting_for_user=True,
        approval_status="pending",
        user_response="Rejected the plan.",
    )
    assert rejected_message["approval_status"] == "rejected"


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
