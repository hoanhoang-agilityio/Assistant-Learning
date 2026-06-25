from langchain_core.tools import BaseTool, tool

from core.agents.state import OrchestrationState


@tool
def read_global_state(state: OrchestrationState) -> dict:
    """Read current orchestration state."""
    ...


@tool
def classify_request(query: str, user_profile: dict, constraints: dict) -> dict:
    """Classify request into request_type and affected_domains."""
    ...


@tool
def route_subgraph(
    route_decision: str | None,
    affected_domains: list[str],
    current_node: str,
) -> dict:
    """Dispatch execution to the next subgraph node."""
    ...


@tool
def partial_rerun_decision(
    verification_report: dict,
    retry_count: int,
    replan_count: int,
) -> dict:
    """Select FIX_REASONING, REPLAN, or RERESEARCH target for partial rerun."""
    ...


@tool
def hitl_control(
    waiting_for_user: bool,
    approval_status: str | None,
    user_response: str | None,
) -> dict:
    """Pause, resume, or reject workflow based on HITL status."""
    ...


@tool
def persist_trigger(
    verification_passed: bool,
    faithfulness_score: float | None,
    approval_status: str | None,
) -> dict:
    """Trigger PERSIST_RESULTS after COMPLETE and user approval."""
    ...


SUPERVISOR_TOOLS: list[BaseTool] = [
    read_global_state,
    classify_request,
    route_subgraph,
    partial_rerun_decision,
    hitl_control,
    persist_trigger,
]
