from typing import TypedDict

from core.agents.state import RouteDecision


class PlanningState(TypedDict):
    """Scoped state for the Planning subgraph.

    Profile extraction/validation now lives entirely in the User subgraph (see
    ``core.subgraphs.user``); by the time Planning runs, ``user_profile`` is already a
    complete, valid, merged profile -- Planning trusts it rather than re-deriving it.
    """

    query: str
    user_profile: dict
    constraints: dict
    request_type: str | None
    workspace_path: str
    route_decision: RouteDecision | None
    revision_feedback: str | None
    approved_tools: list[str]
    reused_execution_plan: bool
