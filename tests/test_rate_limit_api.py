import pytest
from fastapi.testclient import TestClient

from api.deps import reset_orchestrator
from api.main import create_app
from core.config.settings import Settings
from core.graph.service import RunOrchestrator
from core.rate_limit import AIRateLimiter, InMemoryUsageStore


@pytest.fixture
def rate_limited_client(memory_checkpointer) -> TestClient:
    store = InMemoryUsageStore()
    settings = Settings(
        rate_limit_enabled=True,
        rate_limit_daily_max_requests_per_user=1,
        rate_limit_daily_max_tokens_per_user=1_000_000,
        rate_limit_daily_max_cost_usd_per_user=100.0,
    )
    limiter = AIRateLimiter(settings=settings, store=store)
    orchestrator = RunOrchestrator(
        checkpointer=memory_checkpointer,
        rate_limiter=limiter,
    )
    app = create_app(orchestrator=orchestrator)
    with TestClient(app) as client:
        yield client
    reset_orchestrator()


def test_create_run_returns_429_when_daily_request_cap_exceeded(
    rate_limited_client: TestClient,
    complete_profile: dict,
) -> None:
    payload = {
        "query": "I want a 4-day training plan to lose weight with strength training.",
        "user_profile": complete_profile,
        "constraints": {"days_per_week": 4, "equipment": "gym"},
    }
    first = rate_limited_client.post("/runs", json=payload, headers={"X-User-Id": "bob"})
    assert first.status_code == 201

    second = rate_limited_client.post("/runs", json=payload, headers={"X-User-Id": "bob"})
    assert second.status_code == 429
    assert "daily_requests" in second.json()["detail"]
