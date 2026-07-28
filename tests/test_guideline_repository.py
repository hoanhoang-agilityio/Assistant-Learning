"""Tests for GuidelineRepository.

Runs against the real local Postgres instance already used by
core.graph.checkpointer/core.rate_limit.postgres_store/core.graph.run_tracker in this
dev environment (docker-compose's postgres service, pgvector-enabled). Feeds hand-built
vectors directly -- no OpenAI call needed, since embeddings are a repository input, not
something it computes. Calls bootstrap_schema() defensively before constructing the
repository, since repositories no longer create their own schema (see
core.repositories.bootstrap) -- production trusts scripts/bootstrap_fitness_db.py has
already run; tests can't make that assumption about a fresh environment, and the call
is idempotent/cheap.
"""

from __future__ import annotations

import pytest

from core.config.settings import get_settings
from core.knowledge.schema import KnowledgeChunk, KnowledgeDocument, KnowledgeSource
from core.repositories.bootstrap import bootstrap_schema
from core.repositories.guideline_repository import GuidelineRepository

_DIM = 1536


def _one_hot(index: int) -> list[float]:
    vector = [0.0] * _DIM
    vector[index] = 1.0
    return vector


def _partial(index_a: int, index_b: int) -> list[float]:
    vector = [0.0] * _DIM
    vector[index_a] = 0.5
    vector[index_b] = 0.5
    return vector


def _source(doc_id: str) -> KnowledgeSource:
    return KnowledgeSource(id=doc_id, title=f"Title {doc_id}", trust_score=0.9)


def _document(doc_id: str, kind: str = "guideline") -> KnowledgeDocument:
    return KnowledgeDocument(
        id=doc_id, source_id=doc_id, kind=kind, title=f"Title {doc_id}", category="general"
    )


def _chunk(doc_id: str, index: int, content: str = "content") -> KnowledgeChunk:
    return KnowledgeChunk(
        id=f"{doc_id}::{index}", document_id=doc_id, chunk_index=index, content=content
    )


@pytest.fixture
def guideline_repository() -> GuidelineRepository:
    settings = get_settings()
    bootstrap_schema(settings.checkpointer_dsn)
    repository = GuidelineRepository(settings.checkpointer_dsn)
    repository.reset()
    yield repository
    repository.reset()
    repository.close()


def test_upsert_then_search_finds_exact_match(guideline_repository: GuidelineRepository) -> None:
    guideline_repository.upsert(
        _source("doc-1"), _document("doc-1"), [(_chunk("doc-1", 0), _one_hot(0))]
    )
    hits = guideline_repository.search(
        kind="guideline", query_embedding=_one_hot(0), limit=3, min_similarity=0.5
    )
    assert len(hits) == 1
    assert hits[0].document_id == "doc-1"
    assert hits[0].similarity == pytest.approx(1.0)


def test_search_filters_below_min_similarity(guideline_repository: GuidelineRepository) -> None:
    guideline_repository.upsert(
        _source("doc-1"), _document("doc-1"), [(_chunk("doc-1", 0), _one_hot(0))]
    )
    hits = guideline_repository.search(
        kind="guideline", query_embedding=_one_hot(1), limit=3, min_similarity=0.5
    )
    assert hits == []


def test_search_filters_by_kind(guideline_repository: GuidelineRepository) -> None:
    guideline_repository.upsert(
        _source("doc-1"), _document("doc-1", kind="guideline"), [(_chunk("doc-1", 0), _one_hot(0))]
    )
    hits = guideline_repository.search(
        kind="exercise", query_embedding=_one_hot(0), limit=3, min_similarity=0.5
    )
    assert hits == []


def test_upsert_deletes_stale_trailing_chunks_on_reingest_with_fewer_chunks(
    guideline_repository: GuidelineRepository,
) -> None:
    """Regression: re-ingesting a document that now produces fewer chunks must not
    leave orphaned, permanently-searchable stale rows."""
    guideline_repository.upsert(
        _source("doc-1"),
        _document("doc-1"),
        [
            (_chunk("doc-1", 0), _one_hot(0)),
            (_chunk("doc-1", 1), _one_hot(1)),
            (_chunk("doc-1", 2), _one_hot(2)),
        ],
    )
    guideline_repository.upsert(
        _source("doc-1"), _document("doc-1"), [(_chunk("doc-1", 0), _one_hot(0))]
    )
    hits = guideline_repository.search(
        kind="guideline", query_embedding=_one_hot(2), limit=3, min_similarity=0.99
    )
    assert hits == []


def test_search_ranks_by_similarity_not_by_document_id(
    guideline_repository: GuidelineRepository,
) -> None:
    """Regression: DISTINCT ON requires ORDER BY d.id first for its own dedupe pass --
    the final LIMIT must apply to a *second* sort by similarity, not fall out of that
    same id-ordered pass. Uses ids chosen so alphabetical order and similarity order
    disagree (doc-a has the id that sorts first but the lower similarity)."""
    guideline_repository.upsert(
        _source("doc-a"), _document("doc-a"), [(_chunk("doc-a", 0), _partial(5, 6))]
    )
    guideline_repository.upsert(
        _source("doc-z"), _document("doc-z"), [(_chunk("doc-z", 0), _one_hot(5))]
    )
    hits = guideline_repository.search(
        kind="guideline", query_embedding=_one_hot(5), limit=1, min_similarity=0.5
    )
    assert len(hits) == 1
    assert hits[0].document_id == "doc-z"


def test_search_dedupes_to_best_chunk_per_document(
    guideline_repository: GuidelineRepository,
) -> None:
    guideline_repository.upsert(
        _source("doc-1"),
        _document("doc-1"),
        [
            (_chunk("doc-1", 0), _one_hot(0)),
            (_chunk("doc-1", 1), _one_hot(3)),
        ],
    )
    hits = guideline_repository.search(
        kind="guideline", query_embedding=_one_hot(3), limit=5, min_similarity=0.5
    )
    assert len(hits) == 1
    assert hits[0].chunk_id == "doc-1::1"
