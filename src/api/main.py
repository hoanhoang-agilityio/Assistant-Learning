import asyncio
import contextlib
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from api.deps import close_orchestrator_resources, get_orchestrator, get_shadow_eval_store
from api.routes.runs import router as runs_router
from api.routes.users import router as users_router
from core.config.settings import Settings, get_settings
from core.evaluation.shadow_eval import run_shadow_evaluation_batch
from core.graph.service import RunOrchestrator
from core.observability.logging import configure_logging
from core.rate_limit.pricing import validate_model_pricing_coverage


async def _run_periodic_reconciliation(instance: RunOrchestrator, interval_seconds: float) -> None:
    """Re-run orphan reconciliation on a timer for the lifetime of the process.

    Startup reconciliation alone only catches runs orphaned by a *previous*
    process; this catches a run whose own background thread died mid-flight
    without reaching its except/finally handlers while this process is up.
    """
    while True:
        await asyncio.sleep(interval_seconds)
        await asyncio.to_thread(instance.reconcile_orphaned_runs)


async def _run_periodic_shadow_evaluation(
    instance: RunOrchestrator, interval_seconds: float
) -> None:
    """Score recently-completed runs with the real Ragas SDK on a timer, for the
    lifetime of the process (L1 remediation, Phase 2 -- see
    core.evaluation.shadow_eval's module docstring for why this is pull-based).

    Off by default (settings.verification_shadow_eval_enabled) -- this task is
    only ever created when the caller has opted in; production's synchronous
    verification path and pass/fail verdict are untouched either way.
    """
    shadow_store = get_shadow_eval_store()
    while True:
        await asyncio.sleep(interval_seconds)
        await asyncio.to_thread(
            run_shadow_evaluation_batch, history_store=instance, shadow_store=shadow_store
        )


def resolve_cors_origins(settings: Settings) -> list[str]:
    """Explicit, non-wildcard CORS origins for the local Streamlit UI."""
    return [f"http://localhost:{settings.streamlit_port}"]


def add_cors_middleware(app: FastAPI, settings: Settings) -> None:
    allow_origins = resolve_cors_origins(settings)
    allow_credentials = True
    # A wildcard origin combined with credentials is a landmine: browsers
    # reject the combination today, but a future "fix" that reflects the
    # request origin back (instead of removing the wildcard) would silently
    # turn this into a real cross-origin credential-leak path. Assert the
    # unsafe combination can never ship, rather than relying on browser
    # behavior as the only backstop.
    assert "*" not in allow_origins or not allow_credentials, (
        "CORS misconfiguration: wildcard origin must not be combined with allow_credentials=True"
    )
    app.add_middleware(
        CORSMiddleware,
        allow_origins=allow_origins,
        allow_credentials=allow_credentials,
        allow_methods=["*"],
        allow_headers=["*"],
    )


def create_app(orchestrator: RunOrchestrator | None = None) -> FastAPI:
    """Build the FastAPI application."""
    settings = get_settings()

    @asynccontextmanager
    async def lifespan(_app: FastAPI):
        # Configure logging first so every later startup step (pricing
        # validation, orphan reconciliation, MCP wiring) is captured at the
        # configured level and format instead of Python's bare default.
        configure_logging(settings.log_level, settings.log_format)
        # Fail fast on bad DB config and on unpriced models (silent cost
        # mis-reporting/mis-enforcement is worse than a startup crash).
        validate_model_pricing_coverage(
            {
                "openai_standard_model": settings.openai_standard_model,
                "openai_xhigh_model": settings.openai_xhigh_model,
                "anthropic_xhigh_model": settings.anthropic_xhigh_model,
            }
        )
        # Skip real Postgres wiring when a caller injected its own orchestrator
        # (tests) — dependency_overrides bypasses get_orchestrator() for
        # request handling, but the lifespan runs independently of that.
        reconciliation_task: asyncio.Task | None = None
        shadow_eval_task: asyncio.Task | None = None
        if orchestrator is None:
            # get_orchestrator() -> configure_fitness_client_from_settings() ->
            # create_fitness_mcp_client_sync() calls asyncio.run() internally, which raises
            # if invoked directly on this coroutine's own already-running event loop. Run it
            # on a worker thread (no event loop of its own) instead, same as the
            # reconcile_orphaned_runs offload just below.
            instance = await asyncio.to_thread(get_orchestrator)  # fail fast on bad DB config
            # Startup reconciliation: recover runs orphaned by a crash/restart
            # of a *previous* process before this one accepts any traffic.
            await asyncio.to_thread(instance.reconcile_orphaned_runs)
            reconciliation_task = asyncio.create_task(
                _run_periodic_reconciliation(instance, settings.reconciliation_interval_seconds)
            )
            if settings.verification_shadow_eval_enabled:
                shadow_eval_task = asyncio.create_task(
                    _run_periodic_shadow_evaluation(
                        instance, settings.verification_shadow_eval_interval_seconds
                    )
                )
        yield
        if reconciliation_task is not None:
            reconciliation_task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await reconciliation_task
        if shadow_eval_task is not None:
            shadow_eval_task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await shadow_eval_task
        if orchestrator is None:
            close_orchestrator_resources()

    app = FastAPI(
        title="PT AI Core Deep Researcher",
        description="Supervisor-orchestrated fitness training and macro planning API",
        version="0.1.0",
        lifespan=lifespan,
    )
    add_cors_middleware(app, settings)
    app.include_router(runs_router)
    app.include_router(users_router)

    if orchestrator is not None:
        app.dependency_overrides[get_orchestrator] = lambda: orchestrator

    @app.get("/health")
    def health() -> dict[str, str]:
        return {
            "status": "ok",
            "service": "pt-ai-core",
            "log_level": settings.log_level,
            "mock_research": str(settings.mock_research).lower(),
        }

    return app


app = create_app()
