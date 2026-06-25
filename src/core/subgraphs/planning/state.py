from typing import TypedDict


class PlanningState(TypedDict):
    """Scoped state for the Planning subgraph."""

    profile: dict
    missing_fields: list[str]
    todos: list[str]
    planning_output: str | None
