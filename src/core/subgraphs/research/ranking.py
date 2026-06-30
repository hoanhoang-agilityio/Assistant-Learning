"""Hybrid deterministic source ranking."""

import re
from typing import Any

WEIGHT_TAVILY = 0.40
WEIGHT_AUTHORITY = 0.30
WEIGHT_SOURCE_TYPE = 0.20
WEIGHT_FRESHNESS = 0.10

SOURCE_TYPE_KEYWORDS: dict[str, tuple[str, ...]] = {
    "systematic_review": ("systematic review", "meta-analysis", "meta analysis"),
    "guideline": ("guideline", "position stand", "consensus statement", "recommendation"),
    "review": ("review", "narrative review"),
}

FRESHNESS_YEAR_PATTERN = re.compile(r"\b(19|20)\d{2}\b")


def _clamp(value: float, low: float = 0.0, high: float = 1.0) -> float:
    return max(low, min(high, value))


def _normalize_tavily_score(score: float) -> float:
    return _clamp(score)


def _source_type_score(source: dict[str, Any]) -> tuple[float, str]:
    haystack = " ".join(
        [
            str(source.get("title", "")),
            str(source.get("snippet", "")),
        ]
    ).lower()
    for label, keywords in SOURCE_TYPE_KEYWORDS.items():
        if any(keyword in haystack for keyword in keywords):
            if label == "systematic_review":
                return 1.0, label
            if label == "guideline":
                return 0.85, label
            return 0.65, label
    return 0.3, "general"


def _freshness_score(source: dict[str, Any]) -> float:
    haystack = " ".join(
        [
            str(source.get("title", "")),
            str(source.get("snippet", "")),
        ]
    )
    years = [int(match.group(0)) for match in FRESHNESS_YEAR_PATTERN.finditer(haystack)]
    if not years:
        return 0.5
    latest_year = max(years)
    if latest_year >= 2020:
        return 1.0
    if latest_year >= 2015:
        return 0.7
    if latest_year >= 2010:
        return 0.4
    return 0.2


def compute_composite_score(source: dict[str, Any]) -> float:
    """Compute weighted composite ranking score."""
    tavily = _normalize_tavily_score(float(source.get("score", 0.0) or 0.0))
    authority = float(source.get("authority_score", 0.2))
    type_score, _ = _source_type_score(source)
    freshness = _freshness_score(source)
    composite = (
        WEIGHT_TAVILY * tavily
        + WEIGHT_AUTHORITY * authority
        + WEIGHT_SOURCE_TYPE * type_score
        + WEIGHT_FRESHNESS * freshness
    )
    return round(_clamp(composite), 4)


def rank_sources_data(sources: list[dict[str, Any]]) -> dict[str, Any]:
    """Rank sources by composite score descending."""
    scored_sources: list[dict[str, Any]] = []
    for source in sources:
        enriched = dict(source)
        type_score, source_type = _source_type_score(source)
        enriched["source_type_score"] = type_score
        enriched["source_type"] = source_type
        enriched["freshness_score"] = _freshness_score(source)
        enriched["composite_score"] = compute_composite_score(enriched)
        scored_sources.append(enriched)

    ranked = sorted(scored_sources, key=lambda item: item["composite_score"], reverse=True)
    for index, source in enumerate(ranked, start=1):
        source["rank"] = index
    return {"sources": ranked}
