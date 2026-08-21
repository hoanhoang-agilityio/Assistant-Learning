"""FastAPI application entrypoint.

Owns the lifespan: startup wires observability and shuts down shared runtime resources.
The graph itself is built lazily on first request so the app can boot while Postgres is
briefly unavailable.
"""

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from slowapi import _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded
from slowapi.middleware import SlowAPIMiddleware

from src.api.v1.api import api_router
from src.core.configs.config import settings
from src.core.langgraph.runtime import graph_runtime
from src.core.limiter import limiter
from src.core.logging import logger
from src.core.middleware import LoggingContextMiddleware
from src.core.observability import langfuse_init, langfuse_shutdown
from src.services.database import close_engine
from src.services.guard import warm_guard


@asynccontextmanager
async def lifespan(_app: FastAPI) -> AsyncIterator[None]:
    """Start and stop shared application resources."""
    # Before anything can serve a request: a missing signing key must stop the process
    # here rather than at the first login, which would sign tokens with an empty secret.
    settings.validate_auth_secrets()

    langfuse_init()

    await warm_guard()

    logger.info(
        "application_startup",
        project=settings.PROJECT_NAME,
        version=settings.VERSION,
        environment=settings.ENVIRONMENT.value,
    )
    yield
    langfuse_shutdown()
    await graph_runtime.close()
    await close_engine()
    logger.info("application_shutdown")


app = FastAPI(
    title=settings.PROJECT_NAME,
    description=settings.DESCRIPTION,
    version=settings.VERSION,
    docs_url=f"{settings.API_V1_STR}/docs",
    openapi_url=f"{settings.API_V1_STR}/openapi.json",
    lifespan=lifespan,
)

app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)
app.add_middleware(SlowAPIMiddleware)
app.add_middleware(LoggingContextMiddleware)
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.ALLOWED_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(api_router, prefix=settings.API_V1_STR)
