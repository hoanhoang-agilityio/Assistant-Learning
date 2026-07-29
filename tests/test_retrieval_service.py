"""RetrievalService against fakes -- no Postgres, no OpenAI."""

from langchain_core.embeddings import Embeddings

from core.knowledge.retrieval.hybrid_retriever import HybridRetriever
from core.knowledge.retrieval.query_rewriter import PassthroughQueryRewriter
from core.knowledge.retrieval.reranker import IdentityReranker
from core.knowledge.retrieval_service import RetrievalService
from core.knowledge.schema import GuidelineHit


class _FakeEmbeddings(Embeddings):
    def embed_documents(self, texts: list[str]) -> list[list[float]]:
        return [[0.0] for _ in texts]

    def embed_query(self, text: str) -> list[float]:
        return [0.0]


class _FakeGuidelineRepository:
    def __init__(
        self, dense_hits: list[GuidelineHit], keyword_hits: list[GuidelineHit] | None = None
    ) -> None:
        self._dense_hits = dense_hits
        self._keyword_hits = keyword_hits if keyword_hits is not None else dense_hits
        self.last_search_kwargs: dict | None = None
        self.last_keyword_kwargs: dict | None = None

    def search(self, **kwargs) -> list[GuidelineHit]:
        self.last_search_kwargs = kwargs
        return self._dense_hits

    def search_keyword(self, **kwargs) -> list[GuidelineHit]:
        self.last_keyword_kwargs = kwargs
        return self._keyword_hits


def _hit(
    *,
    document_id: str = "doc-1",
    chunk_id: str | None = None,
    trust_score: float = 0.9,
    similarity: float = 0.9,
) -> GuidelineHit:
    return GuidelineHit(
        document_id=document_id,
        chunk_id=chunk_id or f"{document_id}::0",
        title="Title",
        content="Content",
        category="general",
        source_url=None,
        trust_score=trust_score,
        similarity=similarity,
    )


def _build_service(repository: _FakeGuidelineRepository) -> RetrievalService:
    embeddings = _FakeEmbeddings()
    return RetrievalService(
        repository,  # type: ignore[arg-type]
        embeddings,
        query_rewriter=PassthroughQueryRewriter(),
        hybrid_retriever=HybridRetriever(repository, embeddings, candidate_pool=10),
        reranker=IdentityReranker(),
    )


def test_search_runs_rewrite_hybrid_and_rerank_pipeline() -> None:
    repository = _FakeGuidelineRepository([_hit()])
    service = _build_service(repository)
    hits = service.search(
        kind="guideline",
        query="volume",
        goal="muscle_gain",
        equipment="gym",
        limit=3,
        min_similarity=0.75,
    )
    assert hits == [_hit()]
    assert repository.last_search_kwargs is not None
    assert repository.last_search_kwargs["kind"] == "guideline"
    assert repository.last_search_kwargs["query_embedding"] == [0.0]
    assert repository.last_search_kwargs["min_similarity"] == 0.75
    assert repository.last_search_kwargs["goal"] == "muscle_gain"
    assert repository.last_search_kwargs["equipment"] == "gym"
    assert repository.last_keyword_kwargs is not None
    assert repository.last_keyword_kwargs["query"] in {"volume", "volume muscle_gain gym"}


def test_search_returns_top_k_after_rerank() -> None:
    repository = _FakeGuidelineRepository(
        [_hit(document_id="a"), _hit(document_id="b"), _hit(document_id="c")]
    )
    service = _build_service(repository)
    hits = service.search(
        kind="guideline",
        query="volume",
        goal="",
        equipment="",
        limit=2,
        min_similarity=0.4,
    )
    assert len(hits) == 2


def test_has_sufficient_coverage_false_when_below_min_documents() -> None:
    service = _build_service(_FakeGuidelineRepository([]))
    assert not service.has_sufficient_coverage([], min_documents=1, min_trust_score=0.8)


def test_has_sufficient_coverage_true_when_average_trust_meets_floor() -> None:
    service = _build_service(_FakeGuidelineRepository([]))
    hits = [_hit(trust_score=0.9), _hit(trust_score=0.95)]
    assert service.has_sufficient_coverage(hits, min_documents=1, min_trust_score=0.85)


def test_has_sufficient_coverage_false_when_average_trust_below_floor() -> None:
    service = _build_service(_FakeGuidelineRepository([]))
    hits = [_hit(trust_score=0.5)]
    assert not service.has_sufficient_coverage(hits, min_documents=1, min_trust_score=0.85)


def test_has_sufficient_coverage_never_divides_by_zero_with_min_documents_zero() -> None:
    """Regression: min_documents=0 with zero hits must not raise ZeroDivisionError."""
    service = _build_service(_FakeGuidelineRepository([]))
    assert not service.has_sufficient_coverage([], min_documents=0, min_trust_score=0.85)
