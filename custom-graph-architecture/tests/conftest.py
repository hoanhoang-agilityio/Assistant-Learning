"""Shared test fixtures."""

import psycopg
import pytest
from langchain_core.messages import HumanMessage
from openai import AuthenticationError

from src.configs.config import settings
from src.services.llm import chat_model


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


@pytest.fixture(scope="session")
async def require_openai_key() -> None:
    """Skip LLM integration tests when no working OpenAI credentials are configured."""
    if not settings.OPENAI_API_KEY:
        pytest.skip("OPENAI_API_KEY missing: skipping LLM integration tests")
    try:
        await chat_model().ainvoke([HumanMessage(content="ping")])
    except AuthenticationError as exc:
        pytest.skip(f"OpenAI credentials rejected for integration tests: {exc}")
    except Exception as exc:
        pytest.skip(f"LLM integration unavailable: {exc}")
