from typing import TypedDict


class ResearchState(TypedDict):
    """Scoped state for the Research subgraph."""

    research_questions: list[str]
    evidence: list[dict]
    sources: list[dict]
    evidence_summary: str | None
