"""Local knowledge-base retrieval: querying guidelines over MCP and shaping hits
into research sources/evidence."""

import logging
from typing import Any

from core.adapters.mcp.fitness_client import get_fitness_client
from core.adapters.observability.tracing import traced_fitness_mcp_call
from core.capabilities.research.verification import (
    verify_sources_data,
)
from core.config.settings import get_settings
from core.shared.knowledge.schema import GuidelineHit

logger = logging.getLogger(__name__)


def is_local_kb_url(url: str) -> bool:
    """Return True when a URL points at the local knowledge base."""
    normalized = url.strip().lower()
    return normalized.startswith("local-kb://")


def search_guideline_documents(
    *, task: str, goal: str, equipment: str
) -> tuple[list[GuidelineHit], bool]:
    """Ranked guideline documents for a research task, via the Fitness MCP Server's
    search_guidelines tool, plus whether they're sufficient to skip Tavily.

    Every failure mode (feature disabled, client unconfigured, MCP timeout/connection
    error, malformed response, GuidelineHit validation error) degrades identically to
    `([], False)` -- the same shape as "no relevant local match" -- so a Fitness MCP
    outage falls back to Tavily-only research rather than crashing the run.
    """
    settings = get_settings()
    if not settings.local_kb_enabled:
        return [], False
    client = get_fitness_client()
    if client is None:
        return [], False
    try:
        with traced_fitness_mcp_call(
            "search_guidelines", input_data={"task": task, "goal": goal, "equipment": equipment}
        ) as span:
            result = client.search_guidelines(
                query=task,
                goal=goal,
                equipment=equipment,
                limit=settings.local_kb_top_k,
                min_documents=settings.local_kb_min_documents,
                min_trust_score=settings.local_kb_min_trust_score,
            )
            hits = [GuidelineHit.model_validate(item) for item in result.get("documents", [])]
            sufficient = bool(result.get("sufficient_coverage", False))
            if span is not None:
                span.update(output={"document_count": len(hits), "sufficient_coverage": sufficient})
        return hits, sufficient
    except Exception:
        logger.warning(
            "Fitness MCP guideline search failed; falling back to Tavily-only", exc_info=True
        )
        return [], False


def guideline_hits_to_sources(hits: list[GuidelineHit], *, task: str) -> list[dict[str, Any]]:
    sources: list[dict[str, Any]] = []
    for index, hit in enumerate(hits):
        url = hit.source_url or f"local-kb://{hit.document_id}"
        sources.append(
            {
                "source_id": f"local:{hit.document_id}:{index}",
                "title": hit.title,
                "url": url,
                "snippet": hit.content[:300],
                "score": hit.trust_score,
                "provider": "local_kb",
                "research_query": task,
                "verified": True,
                "category": hit.category,
            }
        )
    return sources


def guideline_hits_to_evidence(hits: list[GuidelineHit]) -> list[dict[str, Any]]:
    evidence: list[dict[str, Any]] = []
    for index, hit in enumerate(hits):
        url = hit.source_url or f"local-kb://{hit.document_id}"
        evidence.append(
            {
                "document_id": f"local_doc_{index}",
                "url": url,
                "content": hit.content,
                "provider": "local_kb",
            }
        )
    return evidence


def has_sufficient_research_coverage(
    sources: list[dict[str, Any]],
    evidence: list[dict[str, Any]],
) -> bool:
    """Return True when gathered sources and evidence meet skip-eval thresholds."""
    settings = get_settings()
    verified_sources = verify_sources_data(sources)["sources"]
    verified_count = sum(1 for source in verified_sources if source.get("verified"))
    return (
        len(sources) >= settings.research_min_verified_sources_for_skip_eval
        and verified_count >= settings.research_min_verified_sources_for_skip_eval
        and len(evidence) >= settings.research_min_evidence_docs_for_skip_eval
    )
