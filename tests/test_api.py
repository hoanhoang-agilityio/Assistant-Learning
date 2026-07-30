import json
import time

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from api.deps import reset_orchestrator
from api.main import create_app, resolve_cors_origins
from core.adapters.db.idempotency_store import IdempotencyStore
from core.adapters.db.run_tracker import RunTracker
from core.adapters.mcp.tavily_client import TavilyMCPClient
from core.capabilities.verification.utils import FAITHFULNESS_PASS_THRESHOLD
from core.config.settings import Settings, get_settings
from core.orchestration.graph.service import RunOrchestrator


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
def idempotency_store() -> IdempotencyStore:
    store = IdempotencyStore(get_settings().checkpointer_dsn)
    store.reset()
    yield store
    store.reset()
    store.close()


@pytest.fixture
def run_tracker() -> RunTracker:
    tracker = RunTracker(get_settings().checkpointer_dsn)
    tracker.reset()
    yield tracker
    tracker.reset()
    tracker.close()


@pytest.fixture
def api_client(
    memory_checkpointer,
    mock_tavily_client: TavilyMCPClient,
    idempotency_store: IdempotencyStore,
    run_tracker: RunTracker,
) -> TestClient:
    del mock_tavily_client
    orchestrator = RunOrchestrator(
        checkpointer=memory_checkpointer,
        idempotency_store=idempotency_store,
        run_tracker=run_tracker,
    )
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


def test_list_runs_for_user(api_client: TestClient, complete_profile: dict) -> None:
    headers = {"X-User-Id": "sidebar-user"}
    first = api_client.post(
        "/runs",
        json={
            "query": "First sidebar history run.",
            "user_profile": complete_profile,
            "constraints": {"days_per_week": 4, "equipment": "gym"},
        },
        headers=headers,
    ).json()
    _wait_for_settled(api_client, first["run_id"])
    second = api_client.post(
        "/runs",
        json={
            "query": "Second sidebar history run.",
            "user_profile": complete_profile,
            "constraints": {"days_per_week": 4, "equipment": "gym"},
        },
        headers=headers,
    ).json()
    settled_second = _wait_for_settled(api_client, second["run_id"])

    list_response = api_client.get("/runs", headers=headers)
    assert list_response.status_code == 200
    summaries = list_response.json()
    assert len(summaries) >= 2
    assert summaries[0]["run_id"] == second["run_id"]
    assert summaries[0]["query"] == "Second sidebar history run."
    assert summaries[0]["status"] == settled_second["status"]
    assert isinstance(summaries[0]["steps"], list)
    assert len(summaries[0]["steps"]) > 0

    user_route_response = api_client.get("/users/sidebar-user/runs")
    assert user_route_response.status_code == 200
    assert user_route_response.json()[0]["run_id"] == second["run_id"]


def test_list_runs_requires_user_id(api_client: TestClient) -> None:
    response = api_client.get("/runs")
    assert response.status_code == 400


def test_resume_run_with_decision_type(api_client: TestClient, complete_profile: dict) -> None:
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
        json={"decision_type": "approve"},
    )
    assert resumed.status_code == 200
    assert resumed.json()["status"] == "running"


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


def test_second_resume_of_the_same_run_returns_conflict(
    api_client: TestClient, complete_profile: dict
) -> None:
    """Regression (PR5): a repeated resume request for a run that's already
    been resumed must return 409 Conflict, end-to-end through the real
    /runs/{id}/resume route -- not silently double-process it."""
    created = api_client.post(
        "/runs",
        json={
            "query": "I want a 4-day fat loss strength plan.",
            "user_profile": complete_profile,
            "constraints": {"days_per_week": 4, "equipment": "gym"},
        },
    ).json()
    _wait_for_settled(api_client, created["run_id"])

    first = api_client.post(
        f"/runs/{created['run_id']}/resume",
        json={"user_response": "approve", "approval_status": "approved"},
    )
    second = api_client.post(
        f"/runs/{created['run_id']}/resume",
        json={"user_response": "approve", "approval_status": "approved"},
    )

    assert first.status_code == 200
    assert second.status_code == 409


def test_get_run_not_found(api_client: TestClient) -> None:
    response = api_client.get("/runs/does-not-exist")
    assert response.status_code == 404


def _read_sse_events(response) -> list[dict]:
    events = []
    for line in response.iter_lines():
        if line.startswith("data: "):
            events.append(json.loads(line[len("data: ") :]))
    return events


def test_stream_run_events_returns_404_for_unknown_run(api_client: TestClient) -> None:
    with api_client.stream("GET", "/runs/does-not-exist/events") as response:
        assert response.status_code == 404


def test_stream_run_events_streams_node_updates_then_settles(
    api_client: TestClient, complete_profile: dict
) -> None:
    """GET /runs/{run_id}/events must stream real-time node/subgraph-node
    completions (not just the whole-subgraph granularity /runs/{run_id}
    polling exposes), ending with exactly one run_settled event whose `run`
    payload matches what /runs/{run_id} reports once the run has settled."""
    created = api_client.post(
        "/runs",
        json={
            "query": "I want a 4-day training plan to lose weight with strength training.",
            "user_profile": complete_profile,
            "constraints": {"days_per_week": 4, "equipment": "gym"},
        },
    ).json()
    run_id = created["run_id"]

    with api_client.stream("GET", f"/runs/{run_id}/events") as response:
        assert response.status_code == 200
        events = _read_sse_events(response)

    assert events, "expected at least one streamed event"
    node_updates = [event for event in events if event["type"] == "node_update"]
    settled_events = [event for event in events if event["type"] == "run_settled"]

    # Each capability is a single top-level graph node in the intent-driven
    # architecture (tools run as plain function calls inside it, not as
    # separate graph nodes), so streamed granularity is per-capability.
    steps = {event["step"] for event in node_updates}
    assert "research" in steps
    assert "fitness" in steps
    assert "verification" in steps

    # Exactly one terminal event, and it's the last one.
    assert len(settled_events) == 1
    assert events[-1]["type"] == "run_settled"
    assert settled_events[0]["run"]["status"] == "waiting_hitl"

    polled = api_client.get(f"/runs/{run_id}").json()
    assert settled_events[0]["run"]["status"] == polled["status"]
    assert settled_events[0]["run"]["steps"] == polled["steps"]


def test_stream_run_events_on_already_settled_run_emits_one_event(
    api_client: TestClient, complete_profile: dict
) -> None:
    """Connecting to the events endpoint after a run has already settled (no
    execution in flight) must not hang waiting for events that will never
    come -- it should immediately emit one run_settled snapshot and close."""
    created = api_client.post(
        "/runs",
        json={
            "query": "Build a hypertrophy plan for muscle gain.",
            "user_profile": complete_profile,
            "constraints": {"days_per_week": 4, "equipment": "gym"},
        },
    ).json()
    run_id = created["run_id"]
    _wait_for_settled(api_client, run_id)

    with api_client.stream("GET", f"/runs/{run_id}/events") as response:
        assert response.status_code == 200
        events = _read_sse_events(response)

    assert len(events) == 1
    assert events[0]["type"] == "run_settled"
    assert events[0]["run"]["status"] == "waiting_hitl"


def test_create_run_with_repeated_idempotency_key_returns_the_existing_run(
    api_client: TestClient, complete_profile: dict
) -> None:
    """Regression (PR4): preserve existing API -- same endpoint, same request
    shape (idempotency_key is optional), same response schema -- but a
    repeated key returns the run already created for it instead of a new one."""
    payload = {
        "query": "I want a 4-day training plan to lose weight.",
        "user_profile": complete_profile,
        "constraints": {"days_per_week": 4, "equipment": "gym"},
        "idempotency_key": "checkout-button-click-abc123",
    }

    first = api_client.post("/runs", json=payload)
    second = api_client.post("/runs", json=payload)

    assert first.status_code == 201
    assert second.status_code == 201
    assert first.json()["run_id"] == second.json()["run_id"]


def test_create_run_without_idempotency_key_still_creates_distinct_runs(
    api_client: TestClient, complete_profile: dict
) -> None:
    """Preserve existing API: omitting idempotency_key (as every caller did
    before this change) must behave exactly as before."""
    payload = {
        "query": "I want a 4-day training plan to lose weight.",
        "user_profile": complete_profile,
        "constraints": {"days_per_week": 4, "equipment": "gym"},
    }

    first = api_client.post("/runs", json=payload)
    second = api_client.post("/runs", json=payload)

    assert first.json()["run_id"] != second.json()["run_id"]


def test_cors_origins_are_not_wildcarded() -> None:
    """Regression test for A9: CORS must never combine a wildcard origin with
    credentials -- browsers reject the combination today, but that's not a
    control we should rely on."""
    origins = resolve_cors_origins(Settings())
    assert "*" not in origins


def test_cors_middleware_rejects_wildcard_with_credentials(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The assertion in add_cors_middleware is the backstop for a future
    "fix" that reintroduces a wildcard origin alongside credentials -- assert
    it actually fires rather than trusting it exists."""
    import api.main as main_module

    monkeypatch.setattr(main_module, "resolve_cors_origins", lambda settings: ["*"])
    app = FastAPI()
    with pytest.raises(AssertionError):
        main_module.add_cors_middleware(app, Settings())
