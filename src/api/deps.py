import logging
from functools import lru_cache

from core.config.settings import get_settings
from core.graph.service import RunOrchestrator
from core.mcp.mock_tavily import build_mock_tavily_client
from core.mcp.tavily_client import configure_tavily_client

logger = logging.getLogger(__name__)


def configure_research_client() -> None:
    """Wire Tavily client from settings (real MCP or dev mock)."""
    settings = get_settings()
    if settings.mock_research:
        configure_tavily_client(build_mock_tavily_client())
        logger.warning("MOCK_RESEARCH enabled — Tavily MCP calls are mocked")
        return
    configure_tavily_client(None)


@lru_cache
def get_orchestrator() -> RunOrchestrator:
    configure_research_client()
    return RunOrchestrator()


def reset_orchestrator() -> None:
    get_orchestrator.cache_clear()
