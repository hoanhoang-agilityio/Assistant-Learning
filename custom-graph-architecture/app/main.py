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

from app.api.v1.api import api_router
from app.core.configs.config import settings
from app.core.langgraph.runtime import graph_runtime
from app.core.limiter import limiter
from app.core.logging import logger
from app.services.database import close_engine


@asynccontextmanager
async def lifespan(_app: FastAPI) -> AsyncIterator[None]:
    """Start and stop shared application resources.

    Nothing here connects to Postgres: the checkpointer pool and the graph are created on
    first use so the app still boots — and still answers ``/health`` — while the database
    is briefly unavailable.
    """
    logger.info(
        "application_startup",
        project=settings.PROJECT_NAME,
        version=settings.VERSION,
        environment=settings.ENVIRONMENT.value,
    )
    yield
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
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.ALLOWED_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(api_router, prefix=settings.API_V1_STR)
