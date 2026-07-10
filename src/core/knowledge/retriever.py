"""Lexical retrieval over the local fitness knowledge base."""

import logging
import threading
from typing import Any

from core.config.settings import get_settings
from core.knowledge.schema import KnowledgeDocument
from core.knowledge.store import KnowledgeStore

logger = logging.getLogger(__name__)

_lock = threading.Lock()
_zero_hit_count = 0


class LocalKnowledgeRetriever:
    """Retrieve ranked local documents for research tasks."""

    def __init__(self, store: KnowledgeStore | None = None) -> None:
        self._store = store or KnowledgeStore()

    def retrieve_for_task(
        self,
        *,
        task: str,
        profile: dict[str, Any],
        limit: int | None = None,
    ) -> list[KnowledgeDocument]:
        settings = get_settings()
        resolved_limit = limit or settings.local_kb_top_k
        goal = str(profile.get("goal", ""))
        equipment = str(profile.get("equipment", ""))
        query_terms = _tokenize(f"{task} {goal} {equipment}")
        scored: list[tuple[float, KnowledgeDocument]] = []
        for document in self._store.load_documents():
            score = _score_document(document, query_terms, goal, equipment)
            if score <= 0:
                continue
            scored.append((score, document))
        scored.sort(key=lambda item: item[0], reverse=True)
        if not scored:
            _record_zero_hit_query(task=task, goal=goal, equipment=equipment)
        return [document for _, document in scored[:resolved_limit]]

    def has_sufficient_coverage(
        self,
        *,
        task: str,
        profile: dict[str, Any],
    ) -> bool:
        settings = get_settings()
        if not settings.local_kb_enabled:
            return False
        documents = self.retrieve_for_task(task=task, profile=profile)
        if len(documents) < settings.local_kb_min_documents:
            return False
        average_trust = sum(doc.trust_score for doc in documents) / len(documents)
        return average_trust >= settings.local_kb_min_trust_score

    def documents_to_sources(
        self,
        documents: list[KnowledgeDocument],
        *,
        task: str,
    ) -> list[dict[str, Any]]:
        sources: list[dict[str, Any]] = []
        for index, document in enumerate(documents):
            url = document.source_url or f"local-kb://{document.id}"
            sources.append(
                {
                    "source_id": f"local:{document.id}:{index}",
                    "title": document.title,
                    "url": url,
                    "snippet": document.content[:300],
                    "score": document.trust_score,
                    "provider": "local_kb",
                    "research_query": task,
                    "verified": True,
                    "category": document.category,
                }
            )
        return sources

    def documents_to_evidence(self, documents: list[KnowledgeDocument]) -> list[dict[str, Any]]:
        evidence: list[dict[str, Any]] = []
        for index, document in enumerate(documents):
            url = document.source_url or f"local-kb://{document.id}"
            evidence.append(
                {
                    "document_id": f"local_doc_{index}",
                    "url": url,
                    "content": document.content,
                    "provider": "local_kb",
                }
            )
        return evidence


def _tokenize(text: str) -> set[str]:
    return {token for token in text.lower().replace("-", " ").split() if len(token) > 2}


def _score_document(
    document: KnowledgeDocument,
    query_terms: set[str],
    goal: str,
    equipment: str,
) -> float:
    haystack = " ".join(
        [
            document.title,
            document.content,
            document.category,
            " ".join(document.tags),
            " ".join(document.goal_applicability),
            " ".join(document.equipment_applicability),
        ]
    ).lower()
    haystack_terms = _tokenize(haystack)
    overlap = len(query_terms & haystack_terms)
    if overlap == 0:
        return 0.0
    score = float(overlap) * document.trust_score
    if goal and goal in document.goal_applicability:
        score += 1.5
    if equipment and equipment in document.equipment_applicability:
        score += 0.5
    return score


def _record_zero_hit_query(*, task: str, goal: str, equipment: str) -> None:
    """Log and count a lexical-scoring miss (zero documents matched).

    Measurement-only signal for the L3/N5 decision in
    docs/reports/known_limitations_remediation_plan.md: whether real
    zero-hit-rate evidence justifies moving the local KB off lexical
    scoring onto embeddings. Does not change retrieval behavior.
    """
    global _zero_hit_count
    with _lock:
        _zero_hit_count += 1
    logger.info(
        "Local KB zero-hit query: task=%r goal=%r equipment=%r — no lexical match "
        "in the local corpus",
        task[:160],
        goal,
        equipment,
    )


def get_zero_hit_query_count() -> int:
    """Return the number of zero-hit local KB queries seen (measurement only)."""
    with _lock:
        return _zero_hit_count


def reset_zero_hit_query_count() -> None:
    """Clear the zero-hit counter — used in tests."""
    global _zero_hit_count
    with _lock:
        _zero_hit_count = 0
