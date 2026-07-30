import logging
import time
from functools import lru_cache

from langgraph.checkpoint.base import BaseCheckpointSaver

from core.adapters.db.checkpointer import postgres_checkpointer
from core.adapters.db.idempotency_store import IdempotencyStore
from core.adapters.db.run_history_store import InMemoryRunHistoryStore, RunHistoryStore
from core.adapters.db.run_tracker import RunTracker
from core.adapters.llm.factory import configure_rate_limiter
from core.adapters.mcp.fitness_client import (
    FitnessMCPClient,
    configure_fitness_client,
    create_fitness_mcp_client_sync,
)
from core.adapters.mcp.mock_fitness import build_mock_fitness_client
from core.adapters.mcp.mock_tavily import build_mock_tavily_client
from core.adapters.mcp.tavily_client import configure_tavily_client
from core.adapters.rate_limit import (
    AIRateLimiter,
    InMemoryUsageStore,
    PostgresUsageStore,
    UsageStore,
)
from core.config.settings import Settings, get_settings
from core.evaluation.shadow_eval import InMemoryShadowEvalStore, ShadowEvalStore
from core.orchestration.graph.service import RunOrchestrator

logger = logging.getLogger(__name__)

_usage_store: UsageStore = InMemoryUsageStore()
_postgres_checkpointer_cm = None
_run_tracker: RunTracker | None = None
_idempotency_store: IdempotencyStore | None = None
_run_history_store: RunHistoryStore | InMemoryRunHistoryStore | None = None
_shadow_eval_store: ShadowEvalStore | InMemoryShadowEvalStore | None = None


def configure_research_client() -> None:
    """Wire Tavily client from settings (real MCP or dev mock)."""
    settings = get_settings()
    if settings.mock_research:
        configure_tavily_client(build_mock_tavily_client())
        logger.warning("MOCK_RESEARCH enabled — Tavily MCP calls are mocked")
        return
    configure_tavily_client(None)


def _connect_with_retry(
    settings: Settings, *, max_attempts: int = 5, backoff_seconds: float = 2.0
) -> FitnessMCPClient | None:
    """Bounded retry against a sibling process (the Fitness MCP Server, started
    independently -- see `uv run python -m core.adapters.mcp.fitness_server`) that may not have
    come up yet. Ordinary multi-process local-dev startup ordering, not a race to work
    around -- linear backoff, no external retry library in this repo's dependency set
    to reuse, so this is a plain loop. Returns None (never raises) once attempts are
    exhausted, so a missing Fitness MCP Server degrades the app instead of crashing it.
    """
    for attempt in range(max_attempts):
        try:
            return create_fitness_mcp_client_sync(settings)
        except Exception:
            if attempt == max_attempts - 1:
                return None
            time.sleep(backoff_seconds)
    return None


def configure_fitness_client_from_settings() -> None:
    """Connect to the already-running Fitness MCP Server process, once, at startup.

    Constructed exactly once and cached for the process lifetime (core.adapters.mcp.fitness_client
    never lazily rebuilds) -- unlike configure_research_client()'s Tavily wiring, which
    still rebuilds its client on every uncached call (a pre-existing gap, out of scope
    here). Non-fatal on exhausted retries: guideline retrieval and template caching
    degrade gracefully (Tavily-only research, no-cache workout generation) rather than
    the app failing to start, since neither is on the "app cannot function at all" path
    the Postgres checkpointer's fail-fast startup check protects.
    """
    settings = get_settings()
    if settings.mock_fitness_kb:
        configure_fitness_client(build_mock_fitness_client())
        logger.warning("MOCK_FITNESS_KB enabled — Fitness MCP calls are mocked")
        return
    client = _connect_with_retry(settings)
    if client is None:
        logger.error(
            "Fitness MCP Server unreachable at %s:%s after retries — guideline retrieval "
            "and template caching will degrade gracefully until it recovers.",
            settings.fitness_mcp_host,
            settings.fitness_mcp_port,
        )
    configure_fitness_client(client)


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


def _build_run_history_store(settings: Settings) -> RunHistoryStore | InMemoryRunHistoryStore:
    global _run_history_store
    if settings.use_postgres_checkpointer:
        _run_history_store = RunHistoryStore(settings.checkpointer_dsn)
    else:
        _run_history_store = InMemoryRunHistoryStore()
    return _run_history_store


@lru_cache
def get_shadow_eval_store() -> ShadowEvalStore | InMemoryShadowEvalStore:
    """Built lazily, only when the shadow-eval periodic task actually runs
    (main.py checks settings.verification_shadow_eval_enabled before calling
    this) -- no connection opened at all when the feature is off, which is
    the default."""
    global _shadow_eval_store
    settings = get_settings()
    if settings.use_postgres_checkpointer:
        _shadow_eval_store = ShadowEvalStore(settings.checkpointer_dsn)
    else:
        _shadow_eval_store = InMemoryShadowEvalStore()
    return _shadow_eval_store


@lru_cache
def get_orchestrator() -> RunOrchestrator:
    configure_research_client()
    configure_fitness_client_from_settings()
    limiter = get_rate_limiter()
    configure_rate_limiter(limiter)
    settings = get_settings()
    checkpointer = (
        _open_postgres_checkpointer(settings) if settings.use_postgres_checkpointer else None
    )
    # Orphan reconciliation and idempotency both need a record that survives a
    # restart and is visible to every replica, so it's a no-op without Postgres.
    global _run_tracker, _idempotency_store, _run_history_store
    if settings.use_postgres_checkpointer:
        _run_tracker = RunTracker(settings.checkpointer_dsn)
        _idempotency_store = IdempotencyStore(settings.checkpointer_dsn)
    run_history_store = _build_run_history_store(settings)
    return RunOrchestrator(
        rate_limiter=limiter,
        checkpointer=checkpointer,
        run_tracker=_run_tracker,
        idempotency_store=_idempotency_store,
        run_history_store=run_history_store,
    )


def close_orchestrator_resources() -> None:
    """Close long-lived Postgres connections — call from the app's shutdown/lifespan."""
    global _postgres_checkpointer_cm, _run_tracker, _idempotency_store, _run_history_store
    global _shadow_eval_store
    if _postgres_checkpointer_cm is not None:
        _postgres_checkpointer_cm.__exit__(None, None, None)
        _postgres_checkpointer_cm = None
    if isinstance(_usage_store, PostgresUsageStore):
        _usage_store.close()
    if _run_tracker is not None:
        _run_tracker.close()
        _run_tracker = None
    if _idempotency_store is not None:
        _idempotency_store.close()
        _idempotency_store = None
    if isinstance(_run_history_store, RunHistoryStore):
        _run_history_store.close()
        _run_history_store = None
    if isinstance(_shadow_eval_store, ShadowEvalStore):
        _shadow_eval_store.close()
        _shadow_eval_store = None
    configure_fitness_client(None)


def reset_orchestrator() -> None:
    close_orchestrator_resources()
    get_orchestrator.cache_clear()
    get_rate_limiter.cache_clear()
    get_shadow_eval_store.cache_clear()
    configure_rate_limiter(None)
    global _usage_store
    _usage_store = InMemoryUsageStore()
