import logging
from functools import lru_cache

from core.config.settings import get_settings
from core.graph.service import RunOrchestrator
from core.llm.factory import configure_rate_limiter
from core.mcp.mock_tavily import build_mock_tavily_client
from core.mcp.tavily_client import configure_tavily_client
from core.rate_limit import AIRateLimiter, InMemoryUsageStore

logger = logging.getLogger(__name__)

_usage_store = InMemoryUsageStore()


def configure_research_client() -> None:
    """Wire Tavily client from settings (real MCP or dev mock)."""
    settings = get_settings()
    if settings.mock_research:
        configure_tavily_client(build_mock_tavily_client())
        logger.warning("MOCK_RESEARCH enabled — Tavily MCP calls are mocked")
        return
    configure_tavily_client(None)


@lru_cache
def get_rate_limiter() -> AIRateLimiter:
    return AIRateLimiter(store=_usage_store)


@lru_cache
def get_orchestrator() -> RunOrchestrator:
    configure_research_client()
    limiter = get_rate_limiter()
    configure_rate_limiter(limiter)
    return RunOrchestrator(rate_limiter=limiter)


def reset_orchestrator() -> None:
    get_orchestrator.cache_clear()
    get_rate_limiter.cache_clear()
    configure_rate_limiter(None)
    _usage_store.reset()
