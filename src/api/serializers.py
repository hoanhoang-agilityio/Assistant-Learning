from api.schemas import RunStatusResponse
from core.graph.service import RunStatus


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
        route_decision=status.route_decision,
        request_type=status.request_type,
        final_artifact_path=status.final_artifact_path,
        final_plan=status.final_plan,
        hitl_type=status.hitl_type,
        hitl_message=status.hitl_message,
        refusal_message=status.refusal_message,
        steps=list(status.steps),
        pending_tool=status.pending_tool,
        next_nodes=list(status.next_nodes),
        error_message=status.error_message,
        profile_form=status.profile_form,
    )
