"""Unit tests for rerankers (no OpenAI)."""

from core.shared.knowledge.retrieval.reranker import HeuristicReranker, IdentityReranker
from core.shared.knowledge.schema import GuidelineHit


def _hit(chunk_id: str, similarity: float, trust: float = 0.9) -> GuidelineHit:
    return GuidelineHit(
        document_id=chunk_id.split("::")[0],
        chunk_id=chunk_id,
        title=chunk_id,
        content="body",
        category="general",
        trust_score=trust,
        similarity=similarity,
    )


def test_identity_reranker_truncates_to_top_k() -> None:
    candidates = [_hit("a::0", 0.9), _hit("b::0", 0.8), _hit("c::0", 0.7)]
    result = IdentityReranker().rerank(query="q", candidates=candidates, top_k=2)
    assert [hit.chunk_id for hit in result] == ["a::0", "b::0"]


def test_heuristic_reranker_blends_similarity_and_trust() -> None:
    candidates = [
        _hit("low-sim-high-trust::0", similarity=0.5, trust=1.0),
        _hit("high-sim-low-trust::0", similarity=0.95, trust=0.1),
    ]
    result = HeuristicReranker().rerank(query="q", candidates=candidates, top_k=1)
    # 0.7*0.95 + 0.3*0.1 = 0.695; 0.7*0.5 + 0.3*1.0 = 0.65 → high-sim wins
    assert result[0].chunk_id == "high-sim-low-trust::0"
