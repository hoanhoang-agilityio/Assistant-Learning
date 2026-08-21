"""Shared test fixtures."""

import psycopg
import pytest
from openai import AuthenticationError

from src.core.configs.config import settings
from src.core.langgraph.prompts import build_intent_classifier_messages
from src.services.intent import IntentDecision, _build_classifier


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
    """Skip LLM integration tests when no working classifier credentials are configured."""
    if not settings.OPENAI_API_KEY:
        pytest.skip("OPENAI_API_KEY missing: skipping LLM integration tests")
    try:
        classifier = _build_classifier().with_structured_output(IntentDecision)
        await classifier.ainvoke(
            build_intent_classifier_messages("How much protein should I eat?")
        )
    except AuthenticationError as exc:
        pytest.skip(f"OpenAI credentials rejected for integration tests: {exc}")
    except Exception as exc:
        pytest.skip(f"LLM integration unavailable: {exc}")
