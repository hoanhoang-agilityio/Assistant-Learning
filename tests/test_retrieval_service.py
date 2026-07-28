"""RetrievalService against fakes -- no Postgres, no OpenAI."""

from langchain_core.embeddings import Embeddings

from core.knowledge.retrieval_service import RetrievalService
from core.knowledge.schema import GuidelineHit


class _FakeEmbeddings(Embeddings):
    def embed_documents(self, texts: list[str]) -> list[list[float]]:
        return [[0.0] for _ in texts]

    def embed_query(self, text: str) -> list[float]:
        return [0.0]


class _FakeGuidelineRepository:
    def __init__(self, hits: list[GuidelineHit]) -> None:
        self._hits = hits
        self.last_search_kwargs: dict | None = None

    def search(self, **kwargs) -> list[GuidelineHit]:
        self.last_search_kwargs = kwargs
        return self._hits


def _hit(trust_score: float = 0.9) -> GuidelineHit:
    return GuidelineHit(
        document_id="doc-1",
        chunk_id="doc-1::0",
        title="Title",
        content="Content",
        category="general",
        source_url=None,
        trust_score=trust_score,
        similarity=0.9,
    )


def test_search_embeds_query_and_delegates_to_repository() -> None:
    repository = _FakeGuidelineRepository([_hit()])
    service = RetrievalService(repository, _FakeEmbeddings())
    hits = service.search(
        kind="guideline",
        query="volume",
        goal="muscle_gain",
        equipment="gym",
        limit=3,
        min_similarity=0.75,
    )
    assert hits == [_hit()]
    assert repository.last_search_kwargs == {
        "kind": "guideline",
        "query_embedding": [0.0],
        "limit": 3,
        "min_similarity": 0.75,
    }


def test_has_sufficient_coverage_false_when_below_min_documents() -> None:
    service = RetrievalService(_FakeGuidelineRepository([]), _FakeEmbeddings())
    assert not service.has_sufficient_coverage([], min_documents=1, min_trust_score=0.8)


def test_has_sufficient_coverage_true_when_average_trust_meets_floor() -> None:
    service = RetrievalService(_FakeGuidelineRepository([]), _FakeEmbeddings())
    hits = [_hit(trust_score=0.9), _hit(trust_score=0.95)]
    assert service.has_sufficient_coverage(hits, min_documents=1, min_trust_score=0.85)


def test_has_sufficient_coverage_false_when_average_trust_below_floor() -> None:
    service = RetrievalService(_FakeGuidelineRepository([]), _FakeEmbeddings())
    hits = [_hit(trust_score=0.5)]
    assert not service.has_sufficient_coverage(hits, min_documents=1, min_trust_score=0.85)


def test_has_sufficient_coverage_never_divides_by_zero_with_min_documents_zero() -> None:
    """Regression: min_documents=0 with zero hits must not raise ZeroDivisionError."""
    service = RetrievalService(_FakeGuidelineRepository([]), _FakeEmbeddings())
    assert not service.has_sufficient_coverage([], min_documents=0, min_trust_score=0.85)
