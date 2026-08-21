"""Shared test fixtures."""

import psycopg
import pytest

from src.core.configs.config import settings


@pytest.fixture(scope="session")
def require_postgres() -> None:
    """Skip the test when the configured Postgres is unreachable.

    Keeps the unit suite runnable without ``docker compose up db`` while still failing
    loudly in CI, where the database is expected to be there.
    """
    try:
        with psycopg.connect(settings.psycopg_database_uri, connect_timeout=3) as conn:
            conn.execute("SELECT 1")
    except psycopg.OperationalError as exc:
        pytest.skip(
            f"postgres unavailable at {settings.POSTGRES_HOST}:{settings.POSTGRES_PORT}: {exc}"
        )
