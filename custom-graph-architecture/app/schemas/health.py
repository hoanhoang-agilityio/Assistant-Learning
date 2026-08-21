"""Health endpoint response schema."""

from pydantic import BaseModel, Field


class HealthResponse(BaseModel):
    """Liveness response returned by ``GET /health``."""

    status: str = Field(description="Literal 'ok' when the process is serving")
    service: str = Field(description="Configured project name")
    version: str = Field(description="Application version")
    environment: str = Field(description="Active environment: development, staging or production")
