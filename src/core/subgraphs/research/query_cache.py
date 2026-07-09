"""Short-TTL exact-match cache for Tavily search results.

Catches identical query text issued from different execution-plan tasks or
different runs within a short window. QUERY_PLANNING_SYSTEM_PROMPT's
anti-duplication instruction only prevents repeats within a single task
batch — there's no cross-task or cross-run memory without this.
"""

from __future__ import annotations

import threading
import time
from typing import Any

from core.config.settings import get_settings

_lock = threading.Lock()
_cache: dict[str, tuple[float, dict[str, Any]]] = {}


def _normalize_query(query: str) -> str:
    return " ".join(query.strip().lower().split())


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


def store_search_result(query: str, result: dict[str, Any]) -> None:
    """Cache a Tavily search result under its normalized query text."""
    if get_settings().research_query_cache_ttl_seconds <= 0:
        return
    key = _normalize_query(query)
    with _lock:
        _cache[key] = (time.monotonic(), result)


def reset_tavily_search_cache() -> None:
    """Clear the cache — used in tests."""
    with _lock:
        _cache.clear()
