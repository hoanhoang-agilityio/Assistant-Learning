"""Lexical retrieval over the local fitness knowledge base."""

from typing import Any

from core.config.settings import get_settings
from core.knowledge.schema import KnowledgeDocument
from core.knowledge.store import KnowledgeStore


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
