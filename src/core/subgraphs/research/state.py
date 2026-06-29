from typing import TypedDict


class ResearchState(TypedDict):
    """Scoped state for the Research subgraph."""

    query: str
    request_type: str | None
    workspace_path: str
    todos: list[str]
    research_questions: list[str]
    evidence: list[dict]
    sources: list[dict]
    evidence_summary: str | None
    blocked_by_todos: bool
