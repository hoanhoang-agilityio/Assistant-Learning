"""Health and readiness endpoints."""

from fastapi import APIRouter

from src.configs.config import settings
from src.schemas.health import HealthResponse

router = APIRouter()


@router.get("/health", response_model=HealthResponse)
async def health() -> HealthResponse:
    """Report that the process is up.

    Deliberately does not touch Postgres: this is the container liveness probe, and a brief
    database outage must not restart a process that is otherwise serving.

    Returns:
        HealthResponse: Service name, version and environment.
    """
    return HealthResponse(
        status="ok",
        service=settings.PROJECT_NAME,
        version=settings.VERSION,
        environment=settings.ENVIRONMENT.value,
    )
