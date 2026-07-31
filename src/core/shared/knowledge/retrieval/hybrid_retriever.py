"""Hybrid retrieval: dense (pgvector) + keyword (Postgres FTS) + metadata filters + RRF.

Repository owns SQL; this component only orchestrates channels and fuses ranks.
Returning a candidate pool (not final top-k) lets a downstream reranker improve
precision without forcing the DB to know about ranking models.
"""

from __future__ import annotations

from typing import Protocol

from langchain_core.embeddings import Embeddings

from core.shared.knowledge.retrieval.fusion import DEFAULT_RRF_K, reciprocal_rank_fusion
from core.shared.knowledge.retrieval.types import MetadataFilters, RewrittenQuery
from core.shared.knowledge.schema import GuidelineHit


class GuidelineSearchStore(Protocol):
    """Persistence surface needed by hybrid retrieval (implemented by GuidelineRepository)."""

    def search(
        self,
        *,
        kind: str,
        query_embedding: list[float],
        limit: int,
        min_similarity: float,
        goal: str | None = None,
        equipment: str | None = None,
        category: str | None = None,
    ) -> list[GuidelineHit]: ...

    def search_keyword(
        self,
        *,
        kind: str,
        query: str,
        limit: int,
        goal: str | None = None,
        equipment: str | None = None,
        category: str | None = None,
    ) -> list[GuidelineHit]: ...


class HybridRetriever:
    """Dense + BM25-style lexical search fused with Reciprocal Rank Fusion."""

    def __init__(
        self,
        repository: GuidelineSearchStore,
        embeddings: Embeddings,
        *,
        candidate_pool: int = 50,
        rrf_k: int = DEFAULT_RRF_K,
    ) -> None:
        self._repository = repository
        self._embeddings = embeddings
        self._candidate_pool = candidate_pool
        self._rrf_k = rrf_k

    def retrieve(
        self,
        *,
        kind: str,
        rewritten: RewrittenQuery,
        min_similarity: float,
        caller_goal: str = "",
        caller_equipment: str = "",
    ) -> list[GuidelineHit]:
        filters = self._resolve_filters(
            rewritten.filters, caller_goal=caller_goal, caller_equipment=caller_equipment
        )
        per_channel_limit = self._candidate_pool
        ranked_lists: list[list[GuidelineHit]] = []
        for search_query in rewritten.search_queries:
            dense_hits = self._dense_search(
                kind=kind,
                search_query=search_query,
                min_similarity=min_similarity,
                limit=per_channel_limit,
                filters=filters,
            )
            if dense_hits:
                ranked_lists.append(dense_hits)
            keyword_hits = self._repository.search_keyword(
                kind=kind,
                query=search_query,
                limit=per_channel_limit,
                goal=filters.goal,
                equipment=filters.equipment,
                category=filters.category,
            )
            if keyword_hits:
                ranked_lists.append(keyword_hits)
        if not ranked_lists:
            return []
        return reciprocal_rank_fusion(ranked_lists, k=self._rrf_k, limit=self._candidate_pool)

    def _dense_search(
        self,
        *,
        kind: str,
        search_query: str,
        min_similarity: float,
        limit: int,
        filters: MetadataFilters,
    ) -> list[GuidelineHit]:
        query_vector = self._embeddings.embed_query(search_query)
        return self._repository.search(
            kind=kind,
            query_embedding=query_vector,
            limit=limit,
            min_similarity=min_similarity,
            goal=filters.goal,
            equipment=filters.equipment,
            category=filters.category,
        )

    @staticmethod
    def _resolve_filters(
        rewritten_filters: MetadataFilters,
        *,
        caller_goal: str,
        caller_equipment: str,
    ) -> MetadataFilters:
        """Caller profile hints win when the rewriter left a field empty."""
        return MetadataFilters(
            goal=rewritten_filters.goal or (caller_goal.strip() or None),
            equipment=rewritten_filters.equipment or (caller_equipment.strip() or None),
            category=rewritten_filters.category,
            topics=list(rewritten_filters.topics),
        )
