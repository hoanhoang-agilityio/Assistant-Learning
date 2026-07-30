"""Wiring tests for build_retrieval_service."""

from langchain_core.embeddings import Embeddings

from core.config.settings import Settings
from core.shared.knowledge.retrieval.query_rewriter import PassthroughQueryRewriter
from core.shared.knowledge.retrieval.reranker import HeuristicReranker, IdentityReranker
from core.shared.knowledge.retrieval_service import RetrievalService, build_retrieval_service


class _FakeEmbeddings(Embeddings):
    def embed_documents(self, texts: list[str]) -> list[list[float]]:
        return [[0.0] for _ in texts]

    def embed_query(self, text: str) -> list[float]:
        return [0.0]


class _FakeRepo:
    def search(self, **kwargs):  # noqa: ANN003
        return []

    def search_keyword(self, **kwargs):  # noqa: ANN003
        return []


def test_build_retrieval_service_disables_llm_components_without_api_key() -> None:
    settings = Settings(
        openai_api_key=None,
        fitness_kb_query_rewrite_enabled=True,
        fitness_kb_rerank_enabled=True,
    )
    service = build_retrieval_service(_FakeRepo(), _FakeEmbeddings(), settings)  # type: ignore[arg-type]
    assert isinstance(service, RetrievalService)
    assert isinstance(service._query_rewriter, PassthroughQueryRewriter)
    assert isinstance(service._reranker, HeuristicReranker)


def test_build_retrieval_service_identity_when_rerank_disabled() -> None:
    settings = Settings(
        openai_api_key=None,
        fitness_kb_query_rewrite_enabled=False,
        fitness_kb_rerank_enabled=False,
    )
    service = build_retrieval_service(_FakeRepo(), _FakeEmbeddings(), settings)  # type: ignore[arg-type]
    assert isinstance(service._query_rewriter, PassthroughQueryRewriter)
    assert isinstance(service._reranker, IdentityReranker)
