"""Sits between the Fitness MCP Server's tools and GuidelineRepository.

Owns query embedding and threshold/coverage logic, and is the seam for future keyword
search, metadata filtering, hybrid ranking, and reranking -- none of which exist yet,
but none of which should require touching the MCP tool signature or the repository's
SQL when they're added.
"""

from langchain_core.embeddings import Embeddings

from core.knowledge.schema import GuidelineHit
from core.repositories.guideline_repository import GuidelineRepository


class RetrievalService:
    def __init__(self, repository: GuidelineRepository, embeddings: Embeddings) -> None:
        self._repository = repository
        self._embeddings = embeddings

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
        query_vector = self._embeddings.embed_query(f"{query} {goal} {equipment}")
        return self._repository.search(
            kind=kind, query_embedding=query_vector, limit=limit, min_similarity=min_similarity
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
