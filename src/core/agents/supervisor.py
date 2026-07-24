from datetime import UTC, datetime

from core.agents.intent_judge import judge_user_intent
from core.agents.rerun import partial_rerun_decision_data
from core.agents.run_execution_plan import RunExecutionPlan, resolve_workflow
from core.agents.state import OrchestrationState
from core.agents.supervisor_log import append_supervisor_decision, load_verification_report
from core.agents.tools import (
    SUBMITTED_PLAN_MISSING_MESSAGE,
    VERIFY_WORKFLOW_UNAVAILABLE_MESSAGE,
    check_topic_scope,
    classify_request,
    refusal_message_for,
)
from core.config.settings import get_settings


def supervisor_node(state: OrchestrationState) -> dict:
    """Run supervisor orchestration tools and prepare the next routing decision."""
    updates: dict = {}

    if state["request_type"] is None:
        scope_result = check_topic_scope(state["query"])

        # Routing depends solely on scope_result.decision -- no separate boolean flags.
        # Only ALLOW continues; REJECT/MIXED/CLARIFY all terminate the run immediately
        # (mixed intent must never silently continue to planning with only part of the
        # message -- see ScopeResult's docstring for why the unsupported part is still
        # preserved on scope_result even though the run stops here).
        if scope_result.decision != "ALLOW":
            return {
                # Persisted as a plain dict -- see OrchestrationState.scope_result's
                # docstring for why a ScopeResult instance never goes into checkpointed
                # state directly.
                "scope_result": scope_result.model_dump(),
                "route_decision": "REFUSED",
                "refusal_message": refusal_message_for(scope_result),
            }

        # `query` is never mutated -- it stays the immutable original for the lifetime of
        # the run. `fitness_query` is the copy downstream planning-related subgraphs
        # consume instead (see OrchestrationState's docstring).
        updates["scope_result"] = scope_result.model_dump()
        updates["fitness_query"] = state["query"]

        classification = classify_request(state["query"])
        updates.update(classification)

        if get_settings().run_execution_plan_enabled:
            judgement = judge_user_intent(state["query"])
            plan = resolve_workflow(judgement)
            if plan.workflow == "GenerateWorkflow":
                updates["execution_plan"] = plan.model_dump()
            elif plan.workflow == "VerifyExternalWorkflow":
                if not get_settings().verify_workflow_enabled:
                    updates["route_decision"] = "REFUSED"
                    updates["refusal_message"] = VERIFY_WORKFLOW_UNAVAILABLE_MESSAGE
                elif not (state.get("submitted_plan_text") or "").strip():
                    if judgement.mentions_submitted_plan:
                        updates["submitted_plan_text"] = state["query"]
                        updates["execution_plan"] = plan.model_dump()
                    else:
                        updates["route_decision"] = "REFUSED"
                        updates["refusal_message"] = SUBMITTED_PLAN_MISSING_MESSAGE
                else:
                    updates["execution_plan"] = plan.model_dump()
            elif plan.workflow in ("EditWorkflow", "EditWithReplanWorkflow"):
                if get_settings().edit_workflow_v2_enabled:
                    updates["execution_plan"] = plan.model_dump()

    merged_state: OrchestrationState = {**state, **updates}  # type: ignore[typeddict-item]

    if merged_state["current_node"] == "verification":
        if merged_state["verification_passed"]:
            updates["route_decision"] = "COMPLETE"
        else:
            report = load_verification_report(merged_state["workspace_path"])
            merged_execution_plan = merged_state.get("execution_plan")
            ordered_domains = (
                RunExecutionPlan.model_validate(merged_execution_plan).ordered_domains
                if merged_execution_plan
                else None
            )
            rerun = partial_rerun_decision_data(
                report,
                merged_state["retry_count"],
                merged_state["replan_count"],
                ordered_domains=ordered_domains,
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
