"""Tavily adapter: the only place research talks to the web search/extract
transport. Kept separate so the domain helpers above do not reach for a
process-global MCP client."""

import logging
from typing import Any

from core.mcp.tavily_client import (
    TAVILY_EXTRACT_TOOL,
    TAVILY_SEARCH_TOOL,
    get_tavily_client,
)
from core.observability.tracing import traced_tavily_call
from core.subgraphs.research.query_cache import get_cached_search_result, store_search_result
from core.subgraphs.research.verification import (
    has_explicit_trusted_domains,
    resolve_trusted_domains,
)

logger = logging.getLogger(__name__)


def normalize_search_results(raw_result: dict[str, Any], query: str) -> list[dict[str, Any]]:
    results = raw_result.get("results", raw_result.get("search_results", []))
    if not isinstance(results, list):
        return []

    normalized: list[dict[str, Any]] = []
    for index, item in enumerate(results):
        if not isinstance(item, dict):
            continue
        url = str(item.get("url", ""))
        normalized.append(
            {
                "source_id": f"{query}:{index}",
                "title": str(item.get("title", "Untitled source")),
                "url": url,
                "snippet": str(item.get("content", item.get("snippet", ""))),
                "score": float(item.get("score", 0.0) or 0.0),
                "provider": "tavily",
                "research_query": query,
            }
        )
    return normalized


def search_tavily_data(query: str) -> dict[str, Any]:
    """Run a single Tavily search query and return normalized sources.

    Cached by normalized query text for a short TTL — catches identical
    queries issued from different execution-plan tasks or different runs.
    Cache key intentionally ignores include_domains: it's derived from a
    single process-wide setting, not a per-call variable, so it can never
    differ between two calls with the same query text.
    """
    cached = get_cached_search_result(query)
    if cached is not None:
        return cached

    client = get_tavily_client()
    include_domains = list(resolve_trusted_domains()) if has_explicit_trusted_domains() else None
    with traced_tavily_call(
        TAVILY_SEARCH_TOOL, input_data={"query": query, "include_domains": include_domains}
    ) as span:
        search_result = client.search(query, include_domains)
        sources = normalize_search_results(search_result, query)
        if span is not None:
            raw_keys = sorted(search_result.keys()) if isinstance(search_result, dict) else []
            span.update(
                output={
                    "source_count": len(sources),
                    "sources": sources[:5],
                    "raw_keys": raw_keys,
                }
            )
        if not sources:
            logger.warning("Tavily search returned no sources for query: %s", query[:120])
    result = {"sources": sources, "query": query}
    store_search_result(query, result)
    return result


def normalize_extract_results(raw_result: dict[str, Any]) -> list[dict[str, Any]]:
    results = raw_result.get("results", [])
    if not isinstance(results, list):
        return []

    evidence: list[dict[str, Any]] = []
    for index, item in enumerate(results):
        if not isinstance(item, dict):
            continue
        evidence.append(
            {
                "document_id": f"doc_{index}",
                "url": str(item.get("url", "")),
                "content": str(item.get("raw_content", item.get("content", ""))),
                "provider": "tavily",
            }
        )
    return evidence


def extract_tavily_data(urls: list[str]) -> dict[str, Any]:
    """Extract document content for the given URLs via Tavily MCP."""
    cleaned_urls = [url for url in urls if url]
    if not cleaned_urls:
        return {"evidence": []}

    client = get_tavily_client()
    with traced_tavily_call(TAVILY_EXTRACT_TOOL, input_data={"urls": cleaned_urls}) as span:
        extract_result = client.extract(cleaned_urls)
        evidence = normalize_extract_results(extract_result)
        if span is not None:
            span.update(
                output={
                    "document_count": len(evidence),
                    "urls": cleaned_urls,
                    "raw_keys": sorted(extract_result.keys())
                    if isinstance(extract_result, dict)
                    else [],
                }
            )
        if not evidence:
            logger.warning("Tavily extract returned no documents for urls: %s", cleaned_urls)
    return {"evidence": evidence}
