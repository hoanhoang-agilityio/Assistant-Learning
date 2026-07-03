from typing import TypedDict

from core.agents.state import RouteDecision


class PlanningState(TypedDict):
    """Scoped state for the Planning subgraph."""

    query: str
    user_profile: dict
    constraints: dict
    request_type: str | None
    workspace_path: str
    route_decision: RouteDecision | None
    profile: dict
    missing_fields: list[str]
    todos: list[str]
    execution_plan: dict
    planning_output: str | None
    requires_hitl: bool
    approved_tools: list[str]
    used_llm_extraction: bool
    requires_tool_approval: bool
    reused_execution_plan: bool
