"""Shared test fixtures."""

import psycopg
import pytest

from src.core.configs.config import settings


@pytest.fixture(autouse=True)
def guard_off(monkeypatch: pytest.MonkeyPatch) -> None:
    """Keep the guard's models out of the suite by default."""
    monkeypatch.setattr(settings, "GUARD_ENABLED", False)


@pytest.fixture(scope="session")
def require_postgres() -> None:
    """Skip the test when the configured Postgres is unreachable.

    Keeps the suite runnable without ``docker compose up db``. The ``integration`` marker
    is applied separately, at collection time — a marker added from inside a fixture is
    too late for ``-m`` to see it.
    """
    try:
        with psycopg.connect(settings.psycopg_database_uri, connect_timeout=3) as conn:
            conn.execute("SELECT 1")
    except psycopg.OperationalError as exc:
        pytest.skip(
            f"postgres unavailable at {settings.POSTGRES_HOST}:{settings.POSTGRES_PORT}: {exc}"
        )
