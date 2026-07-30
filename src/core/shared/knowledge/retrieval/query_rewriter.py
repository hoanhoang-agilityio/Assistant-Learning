"""Query understanding: rewrite user text into optimized search queries + filters.

Lives in the retrieval layer (not MCP) so tool signatures stay stable while
query strategy can evolve. Improves recall by expanding synonyms / fitness
jargon and extracts metadata for SQL filters before hybrid search.
"""

from __future__ import annotations

import logging
from typing import Protocol

from langchain_core.messages import HumanMessage, SystemMessage
from pydantic import BaseModel, ConfigDict, Field

from core.shared.knowledge.retrieval.types import MetadataFilters, RewrittenQuery

logger = logging.getLogger(__name__)

_REWRITE_SYSTEM_PROMPT = """\
You rewrite fitness / training guideline search queries for a hybrid retrieval system.

Given the user query and optional profile hints (goal, equipment), produce:
1. One to three optimized search queries (concise, evidence-oriented, no filler).
2. Optional metadata filters when confidently implied (goal, equipment, category).

Rules:
- Always keep the original user intent; do not invent constraints the user did not imply.
- Prefer guideline / exercise-science phrasing (e.g. "weekly set volume hypertrophy").
- category examples: volume, intensity, progressive_overload, recovery, nutrition, general.
- If unsure about a filter, leave it null.
- search_queries must be non-empty; include at least one query close to the original.
"""


class _LlmRewritePayload(BaseModel):
    """Structured LLM output for query rewrite (internal schema)."""

    model_config = ConfigDict(extra="forbid")

    search_queries: list[str] = Field(min_length=1, max_length=5)
    goal: str | None = None
    equipment: str | None = None
    category: str | None = None
    topics: list[str] = Field(default_factory=list)


class QueryRewriter(Protocol):
    def rewrite(self, *, query: str, goal: str = "", equipment: str = "") -> RewrittenQuery: ...


class PassthroughQueryRewriter:
    """No-LLM rewriter: preserves the original query and caller-supplied filters.

    Used in tests and when rewrite is disabled. Still enriches the dense/lexical
    string with goal/equipment the way the legacy embed path did, so disabling
    rewrite does not silently regress recall.
    """

    def rewrite(self, *, query: str, goal: str = "", equipment: str = "") -> RewrittenQuery:
        stripped = query.strip()
        if not stripped:
            raise ValueError("query must be non-empty")
        enriched = " ".join(part for part in (stripped, goal.strip(), equipment.strip()) if part)
        search_queries = [stripped]
        if enriched != stripped:
            search_queries.append(enriched)
        return RewrittenQuery(
            original_query=stripped,
            search_queries=search_queries,
            filters=MetadataFilters(
                goal=goal.strip() or None,
                equipment=equipment.strip() or None,
            ),
        )


class LlmQueryRewriter:
    """LLM-backed query understanding with safe fallback to PassthroughQueryRewriter."""

    def __init__(self, *, fallback: QueryRewriter | None = None) -> None:
        self._fallback = fallback or PassthroughQueryRewriter()

    def rewrite(self, *, query: str, goal: str = "", equipment: str = "") -> RewrittenQuery:
        stripped = query.strip()
        if not stripped:
            raise ValueError("query must be non-empty")
        try:
            from core.adapters.llm.factory import invoke_standard_structured_output

            payload = invoke_standard_structured_output(
                _LlmRewritePayload,
                [
                    SystemMessage(content=_REWRITE_SYSTEM_PROMPT),
                    HumanMessage(
                        content=(
                            f"Original query: {stripped}\n"
                            f"Profile goal hint: {goal or '(none)'}\n"
                            f"Profile equipment hint: {equipment or '(none)'}"
                        )
                    ),
                ],
                prompt_cache_key="fitness-kb-query-rewrite-v1",
            )
        except Exception:
            logger.exception("Query rewrite failed; falling back to passthrough rewriter")
            return self._fallback.rewrite(query=stripped, goal=goal, equipment=equipment)
        return self._build_rewritten(stripped, goal=goal, equipment=equipment, payload=payload)

    def _build_rewritten(
        self,
        original: str,
        *,
        goal: str,
        equipment: str,
        payload: _LlmRewritePayload,
    ) -> RewrittenQuery:
        search_queries: list[str] = []
        for candidate in [original, *payload.search_queries]:
            cleaned = candidate.strip()
            if cleaned and cleaned not in search_queries:
                search_queries.append(cleaned)
        resolved_goal = (payload.goal or goal).strip() or None
        resolved_equipment = (payload.equipment or equipment).strip() or None
        return RewrittenQuery(
            original_query=original,
            search_queries=search_queries,
            filters=MetadataFilters(
                goal=resolved_goal,
                equipment=resolved_equipment,
                category=(payload.category or "").strip() or None,
                topics=[topic.strip() for topic in payload.topics if topic.strip()],
            ),
        )
