from datetime import UTC, datetime

from core.agents.rerun import partial_rerun_decision_data
from core.agents.state import OrchestrationState
from core.agents.supervisor_log import append_supervisor_decision, load_verification_report
from core.agents.tools import check_topic_scope, classify_request


def supervisor_node(state: OrchestrationState) -> dict:
    """Run supervisor orchestration tools and prepare the next routing decision."""
    updates: dict = {}

    if state["request_type"] is None:
        scope = check_topic_scope(state["query"])
        if scope["is_off_topic"]:
            return {
                "route_decision": "REFUSED",
                "refusal_message": scope["refusal_message"],
            }

        classification = classify_request(state["query"])
        updates.update(classification)

    merged_state: OrchestrationState = {**state, **updates}  # type: ignore[typeddict-item]

    if merged_state["current_node"] == "verification":
        if merged_state["verification_passed"]:
            updates["route_decision"] = "COMPLETE"
        else:
            report = load_verification_report(merged_state["workspace_path"])
            rerun = partial_rerun_decision_data(
                report,
                merged_state["retry_count"],
                merged_state["replan_count"],
            )
            updates.update(rerun)
            _log_supervisor_decision(merged_state, report, rerun)

    route_decision = merged_state.get("route_decision")
    if updates.get("route_decision") is not None:
        route_decision = updates["route_decision"]

    approval_status = merged_state["approval_status"]
    if updates.get("approval_status") is not None:
        approval_status = updates["approval_status"]
    if route_decision == "COMPLETE" and approval_status not in {"approved", "rejected"}:
        updates["waiting_for_user"] = True

    return updates


def _log_supervisor_decision(
    state: OrchestrationState,
    verification_report: dict,
    rerun: dict,
) -> None:
    append_supervisor_decision(
        state["workspace_path"],
        {
            "timestamp": datetime.now(UTC).isoformat(),
            "run_id": state["run_id"],
            "thread_id": state["thread_id"],
            "verification_passed": verification_report.get("passed", False),
            "route_decision": rerun.get("route_decision"),
            "retry_count": rerun.get("retry_count", state["retry_count"]),
            "replan_count": rerun.get("replan_count", state["replan_count"]),
            "feedback": verification_report.get("feedback"),
        },
    )
