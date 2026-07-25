"""Test helpers for Research Agent overrides and sample artifacts."""

from typing import Any

from core.subgraphs.research.schema import ResearchAgentResult, ResearchFindings


def default_structured_findings() -> ResearchFindings:
    return ResearchFindings(
        consensus=(
            "Resistance training combined with a moderate caloric deficit supports fat loss "
            "while preserving lean mass for recreationally active adults, per hypertrophy "
            "training evidence from peer-reviewed literature."
        ),
        key_findings=[
            "Progressive resistance training 3-4 days per week supports fat loss outcomes.",
            "Protein intake near 1.6-2.2 g/kg/day aids lean mass retention during cutting.",
            "Training volume should match recovery capacity and activity level.",
        ],
        conflicting_evidence=[
            "Optimal weekly set counts vary across meta-analyses and populations.",
        ],
        limitations=[
            "Most cited guidance is based on general populations, "
            "not individualized medical cases.",
        ],
        recommended_sources=[
            "https://example.edu/fitness-training-hypertrophy",
            "https://example.org/resistance-training-nutrition",
        ],
    )


def default_research_agent_result(
    sources: list[dict[str, Any]] | None = None,
    evidence: list[dict[str, Any]] | None = None,
) -> ResearchAgentResult:
    structured = default_structured_findings()
    resolved_sources = sources or [
        {
            "source_id": "q:0",
            "title": "Hypertrophy training evidence",
            "url": "https://example.edu/fitness-training-hypertrophy",
            "snippet": "hypertrophy training evidence for fat loss",
            "score": 0.95,
            "provider": "tavily",
            "research_query": "fat loss resistance training guideline",
            "verified": True,
            "authority_tier": "whitelist",
            "authority_score": 1.0,
            "composite_score": 0.91,
            "rank": 1,
        },
        {
            "source_id": "q:1",
            "title": "Generic page",
            "url": "https://example.com/page",
            "snippet": "unrelated finance content",
            "score": 0.2,
            "provider": "tavily",
            "research_query": "macro guidance",
            "verified": False,
            "authority_tier": "unverified",
            "authority_score": 0.2,
            "composite_score": 0.25,
            "rank": 2,
        },
    ]
    resolved_evidence = evidence or [
        {
            "document_id": "doc_0",
            "url": "https://example.edu/fitness-training-hypertrophy",
            "content": "Evidence-based hypertrophy and fat loss programming guidance.",
            "provider": "tavily",
        }
    ]
    summary = f"{structured.consensus}\n\nKey findings:\n" + "\n".join(
        f"- {item}" for item in structured.key_findings[:3]
    )
    return ResearchAgentResult(
        sources=resolved_sources,
        evidence=resolved_evidence,
        structured_findings=structured,
        evidence_summary=summary,
        agent_iterations=1,
    )


def research_agent_override(**_kwargs: Any) -> ResearchAgentResult:
    """Deterministic override callable for configure_research_agent."""
    return default_research_agent_result()


def research_agent_override_factory(
    result: ResearchAgentResult,
):
    """Return an override that always returns the given result."""

    def _override() -> ResearchAgentResult:
        return result

    return _override
