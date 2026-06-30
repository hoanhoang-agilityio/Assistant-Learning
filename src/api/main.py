from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from api.deps import get_orchestrator
from api.routes.runs import router as runs_router
from core.config.settings import get_settings
from core.graph.service import RunOrchestrator


def create_app(orchestrator: RunOrchestrator | None = None) -> FastAPI:
    """Build the FastAPI application."""
    settings = get_settings()
    app = FastAPI(
        title="PT AI Core Deep Researcher",
        description="Supervisor-orchestrated fitness training and macro planning API",
        version="0.1.0",
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
