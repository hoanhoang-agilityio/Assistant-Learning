"""Tests for local fitness knowledge base retrieval."""

from pathlib import Path

from core.knowledge.retriever import (
    LocalKnowledgeRetriever,
    get_zero_hit_query_count,
    reset_zero_hit_query_count,
)
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


def test_local_kb_zero_hit_query_is_logged_and_counted() -> None:
    reset_zero_hit_query_count()
    store = KnowledgeStore(
        corpus_path=Path("src/core/knowledge/data/corpus.jsonl"),
    )
    retriever = LocalKnowledgeRetriever(store=store)
    # Empty profile: goal/equipment strings are themselves tokenized into the
    # query, so a non-empty goal/equipment (e.g. "fat_loss", "gym") can match
    # a document's own goal_applicability/equipment_applicability tokens even
    # when the task text is gibberish — leave them unset to get a genuine miss.
    documents = retriever.retrieve_for_task(
        task="xylophone quantum spreadsheet unrelated gibberish",
        profile={},
    )
    assert documents == []
    assert get_zero_hit_query_count() == 1


def test_local_kb_non_zero_hit_does_not_increment_counter() -> None:
    reset_zero_hit_query_count()
    store = KnowledgeStore(
        corpus_path=Path("src/core/knowledge/data/corpus.jsonl"),
    )
    retriever = LocalKnowledgeRetriever(store=store)
    retriever.retrieve_for_task(
        task="Research safe fat-loss rates and caloric deficit limits",
        profile={"goal": "fat_loss", "equipment": "gym"},
    )
    assert get_zero_hit_query_count() == 0
