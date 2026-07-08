"""Tests for local fitness knowledge base retrieval."""

from pathlib import Path

from core.knowledge.retriever import LocalKnowledgeRetriever
from core.knowledge.store import KnowledgeStore


def test_local_kb_retrieves_fat_loss_documents() -> None:
    store = KnowledgeStore(
        corpus_path=Path("src/core/knowledge/data/corpus.jsonl"),
    )
    retriever = LocalKnowledgeRetriever(store=store)
    documents = retriever.retrieve_for_task(
        task="Research safe fat-loss rates and caloric deficit limits",
        profile={"goal": "fat_loss", "equipment": "gym"},
    )
    assert documents
    assert any(doc.category in {"fat_loss", "safety", "nutrition"} for doc in documents)


def test_local_kb_coverage_skips_tavily_for_known_task() -> None:
    store = KnowledgeStore(
        corpus_path=Path("src/core/knowledge/data/corpus.jsonl"),
    )
    retriever = LocalKnowledgeRetriever(store=store)
    has_coverage = retriever.has_sufficient_coverage(
        task="Research safe fat-loss rates and caloric deficit limits",
        profile={"goal": "fat_loss", "equipment": "gym"},
    )
    assert has_coverage is True
