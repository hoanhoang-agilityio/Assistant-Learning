"""Unit tests for Reciprocal Rank Fusion."""

from core.knowledge.retrieval.fusion import reciprocal_rank_fusion
from core.knowledge.schema import GuidelineHit


def _hit(chunk_id: str, similarity: float) -> GuidelineHit:
    return GuidelineHit(
        document_id=chunk_id.split("::")[0],
        chunk_id=chunk_id,
        title=chunk_id,
        content=chunk_id,
        category="general",
        similarity=similarity,
    )


def test_rrf_prefers_items_appearing_in_multiple_lists() -> None:
    dense = [_hit("a::0", 0.9), _hit("b::0", 0.8), _hit("c::0", 0.7)]
    keyword = [_hit("c::0", 0.5), _hit("a::0", 0.4), _hit("d::0", 0.3)]
    fused = reciprocal_rank_fusion([dense, keyword], k=60, limit=3)
    assert [hit.chunk_id for hit in fused] == ["a::0", "c::0", "b::0"]


def test_rrf_keeps_higher_similarity_payload() -> None:
    dense = [_hit("a::0", 0.95)]
    keyword = [_hit("a::0", 0.2)]
    fused = reciprocal_rank_fusion([dense, keyword], limit=1)
    assert fused[0].similarity == 0.95


def test_rrf_empty_lists_return_empty() -> None:
    assert reciprocal_rank_fusion([], limit=5) == []
    assert reciprocal_rank_fusion([[], []], limit=5) == []


def test_rrf_respects_limit() -> None:
    ranked = [_hit(f"d{i}::0", 1.0 - i * 0.1) for i in range(5)]
    fused = reciprocal_rank_fusion([ranked], limit=2)
    assert len(fused) == 2
