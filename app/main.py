"""ASGI entrypoint for the new app flow.

Serves the authentication surface under ``/api/v1/auth``. Referenced by the
Dockerfile as ``app.main:app``.
"""

from contextlib import asynccontextmanager
from datetime import UTC, datetime

from asgi_correlation_id import CorrelationIdMiddleware
from fastapi import FastAPI, Request, status
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from slowapi import _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded

from app.api.v1.api import api_router
from app.core.cache import cache_service
from app.core.configs.config import settings
from app.core.limiter import limiter
from app.core.logging import logger
from app.core.middleware import LoggingContextMiddleware
from app.core.observability import langfuse_init
from app.services.database import database_service
from app.services.memory import memory_service


@asynccontextmanager
async def lifespan(_app: FastAPI):
    """Validate secrets at startup, so a misconfigured deploy fails loudly."""
    # Checked here rather than at import time: Alembic and test collection import
    # settings without needing a production signing key.
    settings.validate_auth_secrets()
    # Before anything traceable runs. The graph and its checkpointer pool are
    # created lazily on first request instead, so the app still boots when
    # Postgres is briefly unavailable.
    langfuse_init()
    # Cache first: the memory service reads through it, and initialising in the
    # other order would leave the first few searches uncached.
    await cache_service.initialize()
    # Pre-warm mem0 so the first real request does not pay its cold init.
    # Both of these log and degrade rather than raising — the app is fully
    # functional without either.
    await memory_service.initialize()
    logger.info(
        "application_startup",
        project_name=settings.PROJECT_NAME,
        version=settings.VERSION,
        environment=settings.ENVIRONMENT.value,
        cache_backend=cache_service.backend,
        memory_enabled=memory_service.enabled,
    )
    yield
    await cache_service.close()
    logger.info("application_shutdown")


app = FastAPI(
    title=settings.PROJECT_NAME,
    version=settings.VERSION,
    description=settings.DESCRIPTION,
    openapi_url=f"{settings.API_V1_STR}/openapi.json",
    lifespan=lifespan,
)

app.add_middleware(LoggingContextMiddleware)
# Outermost, so request_id exists before any other middleware emits a log line.
app.add_middleware(CorrelationIdMiddleware)

app.state.limiter = limiter
# Without both of these, every @limiter.limit decorator raises at request time.
app.add_exception_handler(
    RateLimitExceeded,
    _rate_limit_exceeded_handler,  # pyright: ignore[reportArgumentType]
)

# A wildcard origin with credentials is rejected by browsers and would be a real
# cross-origin credential leak if someone later "fixed" it by reflecting the
# request origin. Refuse to start on that combination instead.
_ALLOW_CREDENTIALS = True
if _ALLOW_CREDENTIALS and "*" in settings.ALLOWED_ORIGINS:
    raise RuntimeError(
        "CORS misconfiguration: ALLOWED_ORIGINS must not contain '*' while "
        "credentials are allowed. Set explicit origins."
    )

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.ALLOWED_ORIGINS,
    allow_credentials=_ALLOW_CREDENTIALS,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.exception_handler(RequestValidationError)
async def validation_exception_handler(
    request: Request, exc: RequestValidationError
) -> JSONResponse:
    """Return field-level validation errors without echoing submitted values."""
    formatted = [
        {
            "field": " -> ".join(str(part) for part in error["loc"] if part != "body"),
            "message": error["msg"],
        }
        for error in exc.errors()
    ]
    return JSONResponse(
        status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
        content={"detail": "Validation error", "errors": formatted},
    )


app.include_router(api_router, prefix=settings.API_V1_STR)


@app.get("/")
@limiter.limit(settings.RATE_LIMIT_ENDPOINTS["root"][0])
async def root(request: Request) -> dict[str, str]:
    """Basic service metadata."""
    return {
        "name": settings.PROJECT_NAME,
        "version": settings.VERSION,
        "status": "healthy",
        "environment": settings.ENVIRONMENT.value,
        "docs_url": "/docs",
    }


@app.get("/health")
@limiter.limit(settings.RATE_LIMIT_ENDPOINTS["health"][0])
async def health_check(request: Request) -> JSONResponse:
    """Report 503 when the database is unreachable, so a load balancer drops us."""
    db_healthy = await database_service.health_check()
    return JSONResponse(
        content={
            "status": "healthy" if db_healthy else "degraded",
            "version": settings.VERSION,
            "environment": settings.ENVIRONMENT.value,
            "components": {
                "api": "healthy",
                "database": "healthy" if db_healthy else "unhealthy",
            },
            "timestamp": datetime.now(UTC).isoformat(),
        },
        status_code=status.HTTP_200_OK if db_healthy else status.HTTP_503_SERVICE_UNAVAILABLE,
    )
