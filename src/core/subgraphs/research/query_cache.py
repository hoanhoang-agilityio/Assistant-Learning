"""Short-TTL exact-match cache for Tavily search results.

Catches identical query text issued from different execution-plan tasks or
different runs within a short window. QUERY_PLANNING_SYSTEM_PROMPT's
anti-duplication instruction only prevents repeats within a single task
batch — there's no cross-task or cross-run memory without this.

Also instruments a near-miss signal (see _record_near_miss_if_overlapping):
whenever a query misses this exact-match cache but its results share source
URLs with a differently-worded cached query, that's evidence a semantic
cache (L5/N3 in docs/reports/known_limitations_remediation_plan.md) would
have avoided the Tavily call. This only measures the signal — it does not
add semantic matching to the cache itself.
"""

from __future__ import annotations

import logging
import threading
import time
from typing import Any

from core.config.settings import get_settings

logger = logging.getLogger(__name__)

_lock = threading.Lock()
_cache: dict[str, tuple[float, dict[str, Any]]] = {}
_near_miss_count = 0
# Near-misses bucketed by overlap fraction (len(overlap)/len(new_urls)) so the
# *shape* of the overlap distribution is visible, not just a running total —
# near-100% clusters suggest true near-duplicate queries (semantic cache would
# help); near-0-20% clusters more likely mean two queries just share one
# generic/high-authority source. Bucket labels are right-closed: "0-20%"
# covers fraction in (0, 0.2].
_near_miss_overlap_buckets: dict[str, int] = {
    "0-20%": 0,
    "20-40%": 0,
    "40-60%": 0,
    "60-80%": 0,
    "80-100%": 0,
}


def _normalize_query(query: str) -> str:
    return " ".join(query.strip().lower().split())


def _result_urls(result: dict[str, Any]) -> set[str]:
    sources = result.get("sources", [])
    if not isinstance(sources, list):
        return set()
    return {
        str(source["url"]) for source in sources if isinstance(source, dict) and source.get("url")
    }


def get_cached_search_result(query: str) -> dict[str, Any] | None:
    """Return a cached Tavily search result if present and not expired."""
    ttl_seconds = get_settings().research_query_cache_ttl_seconds
    if ttl_seconds <= 0:
        return None
    key = _normalize_query(query)
    with _lock:
        entry = _cache.get(key)
        if entry is None:
            return None
        cached_at, result = entry
        if time.monotonic() - cached_at > ttl_seconds:
            del _cache[key]
            return None
        return result


def _overlap_fraction_bucket(fraction: float) -> str:
    """Map an overlap fraction in (0, 1] to a 20%-wide histogram bucket."""
    if fraction <= 0.2:
        return "0-20%"
    if fraction <= 0.4:
        return "20-40%"
    if fraction <= 0.6:
        return "40-60%"
    if fraction <= 0.8:
        return "60-80%"
    return "80-100%"


def _record_near_miss_if_overlapping(normalized_query: str, result: dict[str, Any]) -> None:
    """Log+count when a fresh (cache-miss) query's URLs overlap a differently-
    worded cached query. Caller must already hold _lock. Records at most one
    near-miss (count + one overlap-fraction bucket) per store_search_result
    call, even if multiple cached entries overlap — the store event, not the
    overlap count, is the unit of measurement, so get_near_miss_count() stays
    equal to the sum of get_near_miss_overlap_distribution()'s bucket counts.
    """
    global _near_miss_count
    new_urls = _result_urls(result)
    if not new_urls:
        return
    for other_key, (_, other_result) in _cache.items():
        if other_key == normalized_query:
            continue
        overlap = new_urls & _result_urls(other_result)
        if overlap:
            fraction = len(overlap) / len(new_urls)
            bucket = _overlap_fraction_bucket(fraction)
            _near_miss_count += 1
            _near_miss_overlap_buckets[bucket] += 1
            logger.info(
                "Tavily query cache near-miss: query=%r differs from cached query=%r "
                "shares %d/%d source URL(s) (%.0f%% overlap, bucket=%s)",
                normalized_query[:120],
                other_key[:120],
                len(overlap),
                len(new_urls),
                fraction * 100,
                bucket,
            )
            return


def store_search_result(query: str, result: dict[str, Any]) -> None:
    """Cache a Tavily search result under its normalized query text."""
    if get_settings().research_query_cache_ttl_seconds <= 0:
        return
    key = _normalize_query(query)
    with _lock:
        _record_near_miss_if_overlapping(key, result)
        _cache[key] = (time.monotonic(), result)


def get_near_miss_count() -> int:
    """Return the number of detected near-miss queries (measurement only)."""
    with _lock:
        return _near_miss_count


def get_near_miss_overlap_distribution() -> dict[str, int]:
    """Return near-miss counts bucketed by overlap fraction (measurement only).

    e.g. {"0-20%": 3, "20-40%": 1, "40-60%": 0, "60-80%": 0, "80-100%": 5}.
    Sums to get_near_miss_count(). Use this before picking a semantic-cache
    similarity threshold: a distribution clustered near "80-100%" suggests
    real near-duplicate queries a semantic cache would catch; clustering near
    "0-20%" more likely means two otherwise-unrelated queries just happened
    to share one common/high-authority source.
    """
    with _lock:
        return dict(_near_miss_overlap_buckets)


def reset_tavily_search_cache() -> None:
    """Clear the cache, near-miss counter, and overlap distribution — used in tests."""
    global _near_miss_count
    with _lock:
        _cache.clear()
        _near_miss_count = 0
        for bucket in _near_miss_overlap_buckets:
            _near_miss_overlap_buckets[bucket] = 0
