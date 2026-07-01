import time

import pytest
from fastapi.testclient import TestClient

from api.deps import reset_orchestrator
from api.main import create_app
from core.graph.service import RunOrchestrator
from core.mcp.tavily_client import TavilyMCPClient
from core.subgraphs.verification.utils import FAITHFULNESS_PASS_THRESHOLD


def _wait_for_settled(client: TestClient, run_id: str, *, timeout: float = 60.0) -> dict:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        response = client.get(f"/runs/{run_id}")
        assert response.status_code == 200
        payload = response.json()
        if payload["status"] != "running":
            return payload
        time.sleep(0.2)
    pytest.fail(f"Run {run_id} did not settle within {timeout:.0f} seconds")


@pytest.fixture
def api_client(
    memory_checkpointer,
    mock_tavily_client: TavilyMCPClient,
) -> TestClient:
    del mock_tavily_client
    orchestrator = RunOrchestrator(checkpointer=memory_checkpointer)
    app = create_app(orchestrator=orchestrator)
    with TestClient(app) as client:
        yield client
    reset_orchestrator()


def test_health_endpoint(api_client: TestClient) -> None:
    response = api_client.get("/health")
    assert response.status_code == 200
    assert response.json()["status"] == "ok"


def test_create_run_returns_waiting_hitl(api_client: TestClient, complete_profile: dict) -> None:
    response = api_client.post(
        "/runs",
        json={
            "query": "I want a 4-day training plan to lose weight with strength training.",
            "user_profile": complete_profile,
            "constraints": {"days_per_week": 4, "equipment": "gym"},
        },
    )
    assert response.status_code == 201
    created = response.json()
    assert created["run_id"]
    assert created["status"] == "running"
    payload = _wait_for_settled(api_client, created["run_id"])
    assert payload["status"] == "waiting_hitl"
    assert payload["verification_passed"] is True
    assert payload["faithfulness_score"] >= FAITHFULNESS_PASS_THRESHOLD


def test_get_run_status(api_client: TestClient, complete_profile: dict) -> None:
    created = api_client.post(
        "/runs",
        json={
            "query": "Build a hypertrophy plan for muscle gain.",
            "user_profile": complete_profile,
            "constraints": {"days_per_week": 4, "equipment": "gym"},
        },
    ).json()
    payload = _wait_for_settled(api_client, created["run_id"])
    response = api_client.get(f"/runs/{created['run_id']}")
    assert response.status_code == 200
    assert response.json()["run_id"] == created["run_id"]
    assert response.json()["status"] == payload["status"] == "waiting_hitl"


def test_resume_run_persists_final_plan(api_client: TestClient, complete_profile: dict) -> None:
    created = api_client.post(
        "/runs",
        json={
            "query": "I want a 4-day fat loss strength plan.",
            "user_profile": complete_profile,
            "constraints": {"days_per_week": 4, "equipment": "gym"},
        },
    ).json()
    _wait_for_settled(api_client, created["run_id"])
    resumed = api_client.post(
        f"/runs/{created['run_id']}/resume",
        json={"user_response": "approve", "approval_status": "approved"},
    )
    assert resumed.status_code == 200
    assert resumed.json()["status"] == "running"
    payload = _wait_for_settled(api_client, created["run_id"])
    assert payload["status"] == "completed"
    assert payload["current_node"] == "persist"
    assert payload["final_plan"] is not None
    assert payload["final_artifact_path"] is not None


def test_get_run_not_found(api_client: TestClient) -> None:
    response = api_client.get("/runs/does-not-exist")
    assert response.status_code == 404
