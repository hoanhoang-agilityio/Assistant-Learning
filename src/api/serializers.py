from api.schemas import RunStatusResponse, RunSummaryResponse
from core.orchestration.graph.run_history_store import RunSummary
from core.orchestration.graph.service import RunStatus


def to_run_summary_response(summary: RunSummary) -> RunSummaryResponse:
    return RunSummaryResponse(
        run_id=summary.run_id,
        query=summary.query,
        status=summary.status,
        steps=list(summary.steps),
        updated_at=summary.updated_at,
    )


def to_run_status_response(status: RunStatus) -> RunStatusResponse:
    return RunStatusResponse(
        run_id=status.run_id,
        thread_id=status.thread_id,
        status=status.status,
        current_node=status.current_node,
        query=status.query,
        waiting_for_user=status.waiting_for_user,
        approval_status=status.approval_status,
        verification_passed=status.verification_passed,
        faithfulness_score=status.faithfulness_score,
        intent=status.intent,
        response_mode=status.response_mode,
        active_capability=status.active_capability,
        final_response=status.final_response,
        final_artifact_path=status.final_artifact_path,
        final_plan=status.final_plan,
        hitl_type=status.hitl_type,
        hitl_message=status.hitl_message,
        refusal_message=status.refusal_message,
        steps=list(status.steps),
        next_nodes=list(status.next_nodes),
        error_message=status.error_message,
        profile_form=status.profile_form,
    )
