from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from api.deps import close_orchestrator_resources, get_orchestrator
from api.routes.runs import router as runs_router
from core.config.settings import get_settings
from core.graph.service import RunOrchestrator
from core.rate_limit.pricing import validate_model_pricing_coverage


def create_app(orchestrator: RunOrchestrator | None = None) -> FastAPI:
    """Build the FastAPI application."""
    settings = get_settings()

    @asynccontextmanager
    async def lifespan(_app: FastAPI):
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
        if orchestrator is None:
            get_orchestrator()  # construct eagerly: fail fast on bad DB config
        yield
        if orchestrator is None:
            close_orchestrator_resources()

    app = FastAPI(
        title="PT AI Core Deep Researcher",
        description="Supervisor-orchestrated fitness training and macro planning API",
        version="0.1.0",
        lifespan=lifespan,
    )
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )
    app.include_router(runs_router)

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
