"""Rank fusion utilities for hybrid retrieval."""

from core.knowledge.schema import GuidelineHit

# Classic RRF constant from Cormack et al.; smooths contribution of deep ranks.
DEFAULT_RRF_K = 60


def reciprocal_rank_fusion(
    ranked_lists: list[list[GuidelineHit]],
    *,
    k: int = DEFAULT_RRF_K,
    limit: int,
) -> list[GuidelineHit]:
    """Merge ranked hit lists with Reciprocal Rank Fusion.

    Score(d) = Σ 1 / (k + rank_i(d)) across lists where d appears. Keeps the
    hit payload from the highest dense ``similarity`` seen for that chunk id
    (falls back to the first occurrence). Improves recall by letting keyword
    and dense channels contribute independently without score calibration.
    """
    if limit <= 0:
        return []
    scores: dict[str, float] = {}
    best_hit: dict[str, GuidelineHit] = {}
    for ranked in ranked_lists:
        for rank, hit in enumerate(ranked, start=1):
            chunk_id = hit.chunk_id
            scores[chunk_id] = scores.get(chunk_id, 0.0) + 1.0 / (k + rank)
            existing = best_hit.get(chunk_id)
            if existing is None or hit.similarity > existing.similarity:
                best_hit[chunk_id] = hit
    ordered_ids = sorted(scores.keys(), key=lambda chunk_id: scores[chunk_id], reverse=True)
    return [best_hit[chunk_id] for chunk_id in ordered_ids[:limit]]
