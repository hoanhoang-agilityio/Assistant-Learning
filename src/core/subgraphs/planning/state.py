from typing import TypedDict


class PlanningState(TypedDict):
    """Scoped state for the Planning subgraph."""

    query: str
    user_profile: dict
    constraints: dict
    request_type: str | None
    workspace_path: str
    profile: dict
    missing_fields: list[str]
    todos: list[str]
    planning_output: str | None
    requires_hitl: bool
