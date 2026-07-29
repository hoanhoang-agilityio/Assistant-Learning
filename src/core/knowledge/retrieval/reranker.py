"""Reranking stage: score hybrid candidates and emit final top-k contexts.

Isolated behind a Protocol so callers (RetrievalService / MCP) never depend on
a specific model. Swap Identity → LLM listwise → true cross-encoder without
touching repository SQL or tool signatures.

Cross-encoder-style scoring beats bi-encoder similarity for precision@k because
the model sees query and document jointly; the LLM listwise implementation is
the production default here (no local GPU / sentence-transformers required) and
is intentionally swappable.
"""

from __future__ import annotations

import logging
from typing import Protocol

from langchain_core.messages import HumanMessage, SystemMessage
from pydantic import BaseModel, ConfigDict, Field

from core.knowledge.schema import GuidelineHit

logger = logging.getLogger(__name__)

_RERANK_SYSTEM_PROMPT = """\
You are a relevance reranker for fitness guideline retrieval.
Given a search query and numbered candidate passages, score how well each
passage answers the query for evidence-based training advice.
Return every candidate id with a relevance score from 0.0 to 1.0.
Do not invent ids. Prefer passages that directly support the query.
"""


class Reranker(Protocol):
    def rerank(
        self,
        *,
        query: str,
        candidates: list[GuidelineHit],
        top_k: int,
    ) -> list[GuidelineHit]: ...


class IdentityReranker:
    """Passthrough reranker: preserves hybrid order (tests / rewrite-only mode)."""

    def rerank(
        self,
        *,
        query: str,
        candidates: list[GuidelineHit],
        top_k: int,
    ) -> list[GuidelineHit]:
        del query
        if top_k <= 0:
            return []
        return candidates[:top_k]


class HeuristicReranker:
    """Cheap local rerank: blend vector/lexical similarity with source trust.

    Useful when LLM rerank is disabled but hybrid still produced a pool larger
    than final top-k. Not a cross-encoder — only a deterministic precision nudge.
    """

    def rerank(
        self,
        *,
        query: str,
        candidates: list[GuidelineHit],
        top_k: int,
    ) -> list[GuidelineHit]:
        del query
        if top_k <= 0:
            return []
        scored = sorted(
            candidates,
            key=lambda hit: (0.7 * hit.similarity) + (0.3 * hit.trust_score),
            reverse=True,
        )
        return scored[:top_k]


class _RerankItem(BaseModel):
    model_config = ConfigDict(extra="forbid")

    chunk_id: str = Field(min_length=1)
    relevance: float = Field(ge=0.0, le=1.0)


class _RerankPayload(BaseModel):
    model_config = ConfigDict(extra="forbid")

    scores: list[_RerankItem] = Field(default_factory=list)


class LlmRelevanceReranker:
    """Listwise LLM reranker (cross-encoder equivalent for API-only deployments).

    Scores query×document jointly in one structured call, then reorders. On
    failure falls back to HeuristicReranker so retrieval still returns results.
    """

    def __init__(self, *, fallback: Reranker | None = None, max_chars_per_doc: int = 800) -> None:
        self._fallback = fallback or HeuristicReranker()
        self._max_chars_per_doc = max_chars_per_doc

    def rerank(
        self,
        *,
        query: str,
        candidates: list[GuidelineHit],
        top_k: int,
    ) -> list[GuidelineHit]:
        if top_k <= 0:
            return []
        if not candidates:
            return []
        if len(candidates) <= top_k:
            return list(candidates)
        try:
            from core.llm.factory import invoke_standard_structured_output

            payload = invoke_standard_structured_output(
                _RerankPayload,
                [
                    SystemMessage(content=_RERANK_SYSTEM_PROMPT),
                    HumanMessage(content=self._build_user_prompt(query, candidates)),
                ],
                prompt_cache_key="fitness-kb-rerank-v1",
            )
        except Exception:
            logger.exception("LLM rerank failed; falling back to heuristic reranker")
            return self._fallback.rerank(query=query, candidates=candidates, top_k=top_k)
        return self._apply_scores(candidates, payload, top_k=top_k)

    def _build_user_prompt(self, query: str, candidates: list[GuidelineHit]) -> str:
        lines = [f"Query: {query}", "", "Candidates:"]
        for index, hit in enumerate(candidates, start=1):
            excerpt = hit.content[: self._max_chars_per_doc]
            lines.append(
                f"{index}. id={hit.chunk_id} title={hit.title!r} "
                f"trust={hit.trust_score:.2f}\n{excerpt}"
            )
        return "\n".join(lines)

    @staticmethod
    def _apply_scores(
        candidates: list[GuidelineHit],
        payload: _RerankPayload,
        *,
        top_k: int,
    ) -> list[GuidelineHit]:
        by_id = {hit.chunk_id: hit for hit in candidates}
        scored: list[tuple[float, GuidelineHit]] = []
        seen: set[str] = set()
        for item in payload.scores:
            hit = by_id.get(item.chunk_id)
            if hit is None or item.chunk_id in seen:
                continue
            seen.add(item.chunk_id)
            scored.append((item.relevance, hit))
        for hit in candidates:
            if hit.chunk_id not in seen:
                scored.append((hit.similarity, hit))
        scored.sort(key=lambda pair: pair[0], reverse=True)
        return [hit for _score, hit in scored[:top_k]]
