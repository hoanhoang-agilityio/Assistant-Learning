from typing import Any, TypedDict


class ResearchState(TypedDict):
    """Scoped state for the Research subgraph."""

    query: str
    request_type: str | None
    workspace_path: str
    profile: dict[str, Any]
    execution_plan: dict[str, Any]
    evidence: list[dict]
    sources: list[dict]
    structured_findings: dict[str, Any] | None
    evidence_summary: str | None
    blocked_by_todos: bool
    agent_iterations: int
    is_reresearch: bool
