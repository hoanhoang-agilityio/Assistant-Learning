"""Orchestrates the Fitness KB retrieval pipeline for the Fitness MCP Server.

Pipeline: QueryRewrite → HybridRetrieval (dense + keyword + filters + RRF) →
Rerank → top-k. MCP tools stay unaware of these internals; GuidelineRepository
owns only SQL. Dedicated components keep this class a thin coordinator.

Public ``search`` / ``has_sufficient_coverage`` signatures are preserved so
callers (fitness_server, tests) do not need to change.
"""

import logging

from langchain_core.embeddings import Embeddings

from core.config.settings import Settings, get_settings
from core.knowledge.retrieval.fusion import DEFAULT_RRF_K
from core.knowledge.retrieval.hybrid_retriever import HybridRetriever
from core.knowledge.retrieval.query_rewriter import (
    LlmQueryRewriter,
    PassthroughQueryRewriter,
    QueryRewriter,
)
from core.knowledge.retrieval.reranker import (
    HeuristicReranker,
    IdentityReranker,
    LlmRelevanceReranker,
    Reranker,
)
from core.knowledge.schema import GuidelineHit
from core.repositories.guideline_repository import GuidelineRepository

logger = logging.getLogger(__name__)


class RetrievalService:
    def __init__(
        self,
        repository: GuidelineRepository,
        embeddings: Embeddings,
        *,
        query_rewriter: QueryRewriter | None = None,
        hybrid_retriever: HybridRetriever | None = None,
        reranker: Reranker | None = None,
        candidate_pool: int = 50,
        rrf_k: int = DEFAULT_RRF_K,
    ) -> None:
        self._repository = repository
        self._embeddings = embeddings
        self._query_rewriter = query_rewriter or PassthroughQueryRewriter()
        self._hybrid_retriever = hybrid_retriever or HybridRetriever(
            repository,
            embeddings,
            candidate_pool=candidate_pool,
            rrf_k=rrf_k,
        )
        self._reranker = reranker or IdentityReranker()

    def search(
        self,
        *,
        kind: str,
        query: str,
        goal: str,
        equipment: str,
        limit: int,
        min_similarity: float,
    ) -> list[GuidelineHit]:
        rewritten = self._query_rewriter.rewrite(query=query, goal=goal, equipment=equipment)
        candidates = self._hybrid_retriever.retrieve(
            kind=kind,
            rewritten=rewritten,
            min_similarity=min_similarity,
            caller_goal=goal,
            caller_equipment=equipment,
        )
        if not candidates and rewritten.filters.category:
            # The category filter is *inferred by the LLM rewriter*, and it is
            # applied as a hard SQL constraint (guideline_repository:
            # `d.category = %(category)s`). When the model invents a value that
            # no document carries, every candidate is excluded and this returns
            # nothing -- indistinguishable to the caller from "the knowledge
            # base has nothing relevant". search_guidelines then reports
            # sufficient_coverage=False and research falls back to the open web,
            # silently bypassing the curated corpus.
            #
            # Retry once with only that inferred filter dropped. goal/equipment
            # are caller-supplied (passed separately below) and stay enforced,
            # so this can only ever recover results that a hallucinated category
            # excluded -- it cannot widen a search that already found something.
            logger.info(
                "Retrieval returned no candidates with inferred category=%r; "
                "retrying without it (query=%r)",
                rewritten.filters.category,
                rewritten.original_query,
            )
            relaxed = rewritten.model_copy(
                update={"filters": rewritten.filters.model_copy(update={"category": None})}
            )
            candidates = self._hybrid_retriever.retrieve(
                kind=kind,
                rewritten=relaxed,
                min_similarity=min_similarity,
                caller_goal=goal,
                caller_equipment=equipment,
            )
        return self._reranker.rerank(
            query=rewritten.original_query,
            candidates=candidates,
            top_k=limit,
        )

    def has_sufficient_coverage(
        self,
        hits: list[GuidelineHit],
        *,
        min_documents: int,
        min_trust_score: float,
    ) -> bool:
        # `not hits` guards a ZeroDivisionError below if min_documents is ever
        # configured to 0 -- defaults (1 everywhere) already avoid it via the len()
        # check alone, but the guard is free and removes the landmine entirely.
        if not hits or len(hits) < min_documents:
            return False
        return (sum(hit.trust_score for hit in hits) / len(hits)) >= min_trust_score


def build_retrieval_service(
    repository: GuidelineRepository,
    embeddings: Embeddings,
    settings: Settings | None = None,
) -> RetrievalService:
    """Wire production retrieval components from settings (used by Fitness MCP)."""
    resolved = settings or get_settings()
    query_rewriter: QueryRewriter
    if resolved.fitness_kb_query_rewrite_enabled and resolved.openai_api_key:
        query_rewriter = LlmQueryRewriter()
    else:
        query_rewriter = PassthroughQueryRewriter()
    reranker: Reranker
    if resolved.fitness_kb_rerank_enabled and resolved.openai_api_key:
        reranker = LlmRelevanceReranker()
    elif resolved.fitness_kb_rerank_enabled:
        reranker = HeuristicReranker()
    else:
        reranker = IdentityReranker()
    return RetrievalService(
        repository,
        embeddings,
        query_rewriter=query_rewriter,
        hybrid_retriever=HybridRetriever(
            repository,
            embeddings,
            candidate_pool=resolved.fitness_kb_candidate_pool,
            rrf_k=resolved.fitness_kb_rrf_k,
        ),
        reranker=reranker,
        candidate_pool=resolved.fitness_kb_candidate_pool,
        rrf_k=resolved.fitness_kb_rrf_k,
    )
