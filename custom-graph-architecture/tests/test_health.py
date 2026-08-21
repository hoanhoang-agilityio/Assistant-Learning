"""Smoke tests for the application skeleton."""

from fastapi.testclient import TestClient

from app.core.configs.config import settings
from app.main import app


def test_health_endpoint_reports_service_metadata() -> None:
    """The liveness probe answers 200 with the configured service identity."""
    with TestClient(app) as client:
        response = client.get(f"{settings.API_V1_STR}/health")

    assert response.status_code == 200
    assert response.json() == {
        "status": "ok",
        "service": settings.PROJECT_NAME,
        "version": settings.VERSION,
        "environment": settings.ENVIRONMENT.value,
    }


def test_database_uris_name_psycopg3_for_sqlalchemy_only() -> None:
    """SQLAlchemy gets the ``+psycopg`` driver prefix; the raw psycopg DSN must not have it."""
    assert settings.sqlalchemy_database_uri.startswith("postgresql+psycopg://")
    assert settings.psycopg_database_uri.startswith("postgresql://")
