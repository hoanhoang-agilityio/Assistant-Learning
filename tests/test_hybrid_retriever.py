"""Unit tests for HybridRetriever against an in-memory fake store."""

from langchain_core.embeddings import Embeddings

from core.knowledge.retrieval.hybrid_retriever import HybridRetriever
from core.knowledge.retrieval.types import MetadataFilters, RewrittenQuery
from core.knowledge.schema import GuidelineHit


class _FakeEmbeddings(Embeddings):
    def embed_documents(self, texts: list[str]) -> list[list[float]]:
        return [[0.0] for _ in texts]

    def embed_query(self, text: str) -> list[float]:
        return [1.0]


class _FakeStore:
    def __init__(self) -> None:
        self.dense_calls: list[dict] = []
        self.keyword_calls: list[dict] = []

    def search(self, **kwargs) -> list[GuidelineHit]:
        self.dense_calls.append(kwargs)
        return [
            GuidelineHit(
                document_id="dense-1",
                chunk_id="dense-1::0",
                title="Dense",
                content="dense match",
                category="volume",
                similarity=0.9,
            )
        ]

    def search_keyword(self, **kwargs) -> list[GuidelineHit]:
        self.keyword_calls.append(kwargs)
        return [
            GuidelineHit(
                document_id="kw-1",
                chunk_id="kw-1::0",
                title="Keyword",
                content="keyword match",
                category="volume",
                similarity=0.5,
            )
        ]


def test_hybrid_retriever_calls_both_channels_and_fuses() -> None:
    store = _FakeStore()
    retriever = HybridRetriever(store, _FakeEmbeddings(), candidate_pool=10)
    rewritten = RewrittenQuery(
        original_query="weekly volume",
        search_queries=["weekly volume"],
        filters=MetadataFilters(goal="muscle_gain", equipment="gym"),
    )
    hits = retriever.retrieve(
        kind="guideline",
        rewritten=rewritten,
        min_similarity=0.4,
        caller_goal="muscle_gain",
        caller_equipment="gym",
    )
    assert {hit.chunk_id for hit in hits} == {"dense-1::0", "kw-1::0"}
    assert len(store.dense_calls) == 1
    assert len(store.keyword_calls) == 1
    assert store.dense_calls[0]["goal"] == "muscle_gain"
    assert store.keyword_calls[0]["equipment"] == "gym"


def test_hybrid_retriever_runs_each_rewritten_query() -> None:
    store = _FakeStore()
    retriever = HybridRetriever(store, _FakeEmbeddings(), candidate_pool=10)
    rewritten = RewrittenQuery(
        original_query="volume",
        search_queries=["volume", "hypertrophy set volume"],
        filters=MetadataFilters(),
    )
    retriever.retrieve(kind="guideline", rewritten=rewritten, min_similarity=0.4)
    assert len(store.dense_calls) == 2
    assert len(store.keyword_calls) == 2
