import logging
from functools import lru_cache

from langgraph.checkpoint.base import BaseCheckpointSaver

from core.config.settings import Settings, get_settings
from core.graph.checkpointer import postgres_checkpointer
from core.graph.service import RunOrchestrator
from core.llm.factory import configure_rate_limiter
from core.mcp.mock_tavily import build_mock_tavily_client
from core.mcp.tavily_client import configure_tavily_client
from core.rate_limit import AIRateLimiter, InMemoryUsageStore, PostgresUsageStore, UsageStore

logger = logging.getLogger(__name__)

_usage_store: UsageStore = InMemoryUsageStore()
_postgres_checkpointer_cm = None


def configure_research_client() -> None:
    """Wire Tavily client from settings (real MCP or dev mock)."""
    settings = get_settings()
    if settings.mock_research:
        configure_tavily_client(build_mock_tavily_client())
        logger.warning("MOCK_RESEARCH enabled — Tavily MCP calls are mocked")
        return
    configure_tavily_client(None)


def _build_usage_store(settings: Settings) -> UsageStore:
    global _usage_store
    if settings.use_postgres_rate_limit_store:
        _usage_store = PostgresUsageStore(settings.checkpointer_dsn)
    else:
        _usage_store = InMemoryUsageStore()
    return _usage_store


def _open_postgres_checkpointer(settings: Settings) -> BaseCheckpointSaver:
    """Open postgres_checkpointer()'s context manager and keep it alive for the process.

    postgres_checkpointer() is a @contextmanager (yields a PostgresSaver);
    RunOrchestrator holds onto the checkpointer for its own lifetime rather
    than per-call, so the context is entered once here and exited from
    close_orchestrator_resources() at app shutdown instead of a `with` block.
    """
    global _postgres_checkpointer_cm
    context_manager = postgres_checkpointer(settings)
    checkpointer = context_manager.__enter__()  # raises before we ever store a half-entered CM
    _postgres_checkpointer_cm = context_manager
    return checkpointer


@lru_cache
def get_rate_limiter() -> AIRateLimiter:
    settings = get_settings()
    store = _build_usage_store(settings)
    return AIRateLimiter(settings=settings, store=store)


@lru_cache
def get_orchestrator() -> RunOrchestrator:
    configure_research_client()
    limiter = get_rate_limiter()
    configure_rate_limiter(limiter)
    settings = get_settings()
    checkpointer = (
        _open_postgres_checkpointer(settings) if settings.use_postgres_checkpointer else None
    )
    return RunOrchestrator(rate_limiter=limiter, checkpointer=checkpointer)


def close_orchestrator_resources() -> None:
    """Close long-lived Postgres connections — call from the app's shutdown/lifespan."""
    global _postgres_checkpointer_cm
    if _postgres_checkpointer_cm is not None:
        _postgres_checkpointer_cm.__exit__(None, None, None)
        _postgres_checkpointer_cm = None
    if isinstance(_usage_store, PostgresUsageStore):
        _usage_store.close()


def reset_orchestrator() -> None:
    close_orchestrator_resources()
    get_orchestrator.cache_clear()
    get_rate_limiter.cache_clear()
    configure_rate_limiter(None)
    global _usage_store
    _usage_store = InMemoryUsageStore()
