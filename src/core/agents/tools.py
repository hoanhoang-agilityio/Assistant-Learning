from langchain_core.tools import BaseTool, tool

from core.agents.rerun import partial_rerun_decision_data
from core.agents.state import AffectedDomain, OrchestrationState, RequestType
from core.hitl.utils import hitl_control_data
from core.persist.utils import persist_trigger_data

REQUEST_TYPE_KEYWORDS: list[tuple[RequestType, tuple[str, ...]]] = [
    ("fat_loss", ("lose weight", "fat loss", "cutting", "cut ")),
    ("muscle_gain", ("muscle gain", "bulk", "hypertrophy", "build muscle")),
    ("macro_calculation", ("macro", "calories", "protein", "macros")),
    ("strength", ("strength", "powerlifting", "1rm")),
    ("endurance", ("endurance", "marathon", "cardio")),
    ("training_plan", ("training plan", "workout plan", "program")),
]

DEFAULT_AFFECTED_DOMAINS: list[AffectedDomain] = [
    "planning",
    "research",
    "fitness",
    "verify",
]


@tool
def read_global_state(state: OrchestrationState) -> dict:
    """Read current orchestration state."""
    return {
        "run_id": state["run_id"],
        "thread_id": state["thread_id"],
        "current_node": state["current_node"],
        "query": state["query"],
        "request_type": state["request_type"],
        "affected_domains": state["affected_domains"],
        "route_decision": state["route_decision"],
        "retry_count": state["retry_count"],
        "replan_count": state["replan_count"],
        "verification_passed": state["verification_passed"],
        "faithfulness_score": state["faithfulness_score"],
        "waiting_for_user": state["waiting_for_user"],
        "approval_status": state["approval_status"],
        "workspace_path": state["workspace_path"],
        "final_artifact_path": state["final_artifact_path"],
    }


@tool
def classify_request(query: str) -> dict:
    """Classify request into request_type and affected_domains."""
    query_lower = query.lower()
    request_type: RequestType = "general_fitness"

    for candidate_type, keywords in REQUEST_TYPE_KEYWORDS:
        if any(keyword in query_lower for keyword in keywords):
            request_type = candidate_type
            break

    return {
        "request_type": request_type,
        "affected_domains": list(DEFAULT_AFFECTED_DOMAINS),
    }


@tool
def partial_rerun_decision(
    verification_report: dict,
    retry_count: int,
    replan_count: int,
) -> dict:
    """Select FIX_REASONING, REPLAN, or RERESEARCH target for partial rerun."""
    return partial_rerun_decision_data(verification_report, retry_count, replan_count)


@tool
def hitl_control(
    waiting_for_user: bool,
    approval_status: str | None,
    user_response: str | None,
) -> dict:
    """Pause, resume, or reject workflow based on HITL status."""
    return hitl_control_data(waiting_for_user, approval_status, user_response)


@tool
def persist_trigger(
    verification_passed: bool,
    faithfulness_score: float | None,
    approval_status: str | None,
) -> dict:
    """Trigger PERSIST_RESULTS after COMPLETE and user approval."""
    return persist_trigger_data(verification_passed, faithfulness_score, approval_status)


SUPERVISOR_TOOLS: list[BaseTool] = [
    read_global_state,
    classify_request,
    partial_rerun_decision,
    hitl_control,
    persist_trigger,
]
