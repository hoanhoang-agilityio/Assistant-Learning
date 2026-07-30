"""Tests for the Tavily exact-match query cache and its near-miss instrumentation."""

from core.capabilities.research.query_cache import (
    get_cached_search_result,
    get_near_miss_count,
    get_near_miss_overlap_distribution,
    reset_tavily_search_cache,
    store_search_result,
)


def test_store_and_get_cached_search_result_exact_match() -> None:
    result = {"query": "protein intake for muscle gain", "sources": [{"url": "https://a.example"}]}
    store_search_result("protein intake for muscle gain", result)
    cached = get_cached_search_result("  Protein Intake For Muscle Gain  ")
    assert cached == result


def test_get_cached_search_result_misses_for_unseen_query() -> None:
    assert get_cached_search_result("never stored before") is None


def test_near_miss_detected_for_differently_worded_overlapping_query() -> None:
    reset_tavily_search_cache()
    store_search_result(
        "protein intake for muscle gain",
        {"sources": [{"url": "https://a.example"}, {"url": "https://b.example"}]},
    )
    assert get_near_miss_count() == 0

    # Different query text, shares 1 of 2 new URLs (50% overlap) with the cached
    # result above.
    store_search_result(
        "macro targets for hypertrophy",
        {"sources": [{"url": "https://b.example"}, {"url": "https://c.example"}]},
    )
    assert get_near_miss_count() == 1
    assert get_near_miss_overlap_distribution()["40-60%"] == 1


def test_no_near_miss_when_queries_share_no_urls() -> None:
    reset_tavily_search_cache()
    store_search_result(
        "protein intake for muscle gain", {"sources": [{"url": "https://a.example"}]}
    )
    store_search_result("safe fat loss rate", {"sources": [{"url": "https://z.example"}]})
    assert get_near_miss_count() == 0
    assert get_near_miss_overlap_distribution() == {
        "0-20%": 0,
        "20-40%": 0,
        "40-60%": 0,
        "60-80%": 0,
        "80-100%": 0,
    }


def test_no_near_miss_against_own_cache_entry() -> None:
    reset_tavily_search_cache()
    # Re-storing under the same normalized key should never count as a near-miss
    # against itself.
    store_search_result("protein intake", {"sources": [{"url": "https://a.example"}]})
    store_search_result("Protein Intake", {"sources": [{"url": "https://a.example"}]})
    assert get_near_miss_count() == 0


def test_near_miss_overlap_distribution_buckets_high_overlap_separately_from_low() -> None:
    reset_tavily_search_cache()
    store_search_result(
        "protein intake for muscle gain",
        {"sources": [{"url": f"https://shared-{i}.example"} for i in range(5)]},
    )

    # Near-identical query: shares all 5 URLs with the cached entry (100% overlap).
    store_search_result(
        "protein intake muscle gain",
        {"sources": [{"url": f"https://shared-{i}.example"} for i in range(5)]},
    )

    # Unrelated-topic query that happens to share just 1 of 5 URLs (20% overlap)
    # with the first cached entry — e.g. both cite one common guideline page.
    store_search_result(
        "unrelated topic entirely",
        {
            "sources": [
                {"url": "https://shared-0.example"},
                {"url": "https://only-here-1.example"},
                {"url": "https://only-here-2.example"},
                {"url": "https://only-here-3.example"},
                {"url": "https://only-here-4.example"},
            ]
        },
    )

    assert get_near_miss_count() == 2
    distribution = get_near_miss_overlap_distribution()
    assert distribution["80-100%"] == 1
    assert distribution["0-20%"] == 1
