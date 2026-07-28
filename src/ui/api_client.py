from __future__ import annotations

import json
import os
import time
from collections.abc import Callable, Iterator
from typing import Any

import httpx

DEFAULT_API_BASE_URL = "http://localhost:8000"
DEFAULT_REQUEST_TIMEOUT = 30.0
DEFAULT_POLL_INTERVAL = 2.0
DEFAULT_RUN_POLL_TIMEOUT = 900.0
DEFAULT_UI_USER_ID = os.getenv("UI_USER_ID", "anonymous")


def get_api_base_url() -> str:
    return os.getenv("API_BASE_URL", DEFAULT_API_BASE_URL).rstrip("/")


def get_ui_user_id() -> str:
    return os.getenv("UI_USER_ID", DEFAULT_UI_USER_ID)


def _request_headers() -> dict[str, str]:
    return {"X-User-Id": get_ui_user_id()}


def create_run(
    client: httpx.Client,
    *,
    query: str,
    user_profile: dict[str, Any],
    constraints: dict[str, Any],
) -> dict[str, Any]:
    response = client.post(
        "/runs",
        json={
            "query": query,
            "user_profile": user_profile,
            "constraints": constraints,
        },
        headers=_request_headers(),
    )
    response.raise_for_status()
    return response.json()


def get_run(client: httpx.Client, run_id: str) -> dict[str, Any]:
    response = client.get(f"/runs/{run_id}", headers=_request_headers())
    response.raise_for_status()
    return response.json()


def list_runs(
    client: httpx.Client,
    *,
    user_id: str | None = None,
    limit: int = 50,
) -> list[dict[str, Any]]:
    params: dict[str, Any] = {"limit": limit}
    if user_id is not None:
        params["user_id"] = user_id
    response = client.get("/runs", params=params, headers=_request_headers())
    response.raise_for_status()
    return response.json()


def poll_run_until_settled(
    client: httpx.Client,
    run_id: str,
    *,
    timeout: float = DEFAULT_RUN_POLL_TIMEOUT,
    interval: float = DEFAULT_POLL_INTERVAL,
    on_progress: Callable[[dict[str, Any]], None] | None = None,
) -> dict[str, Any]:
    """Poll run status until it leaves the running state or the timeout expires."""
    deadline = time.monotonic() + timeout
    latest_status: dict[str, Any] | None = None
    while time.monotonic() < deadline:
        latest_status = get_run(client, run_id)
        if on_progress is not None:
            on_progress(latest_status)
        if latest_status.get("status") != "running":
            return latest_status
        time.sleep(interval)
    if latest_status is not None:
        return latest_status
    raise httpx.TimeoutException(
        f"Run {run_id} did not finish within {timeout:.0f} seconds",
        request=None,
    )


def stream_run_events(
    client: httpx.Client,
    run_id: str,
    *,
    timeout: float = DEFAULT_RUN_POLL_TIMEOUT,
) -> Iterator[dict[str, Any]]:
    """Consume GET /runs/{run_id}/events, yielding each parsed SSE event.

    Each event is either {"type": "node_update", "step": "<subgraph>:<node>"}
    (or a bare top-level node name) or the terminal
    {"type": "run_settled", "run": <RunStatus dict>}.
    """
    with client.stream(
        "GET",
        f"/runs/{run_id}/events",
        timeout=timeout,
    ) as response:
        response.raise_for_status()
        for line in response.iter_lines():
            if not line.startswith("data: "):
                continue
            yield json.loads(line[len("data: ") :])


def stream_run_until_settled(
    client: httpx.Client,
    run_id: str,
    *,
    timeout: float = DEFAULT_RUN_POLL_TIMEOUT,
    interval: float = DEFAULT_POLL_INTERVAL,
    on_progress: Callable[[dict[str, Any]], None] | None = None,
) -> dict[str, Any]:
    """Drive on_progress from the run's live SSE event stream and return the
    settled status, instead of waiting for a whole subgraph (or the poll
    interval) before the caller sees any update.

    Accumulates streamed step ids into the same {"steps": [...]} shape
    poll_run_until_settled's status dict already carries, so on_progress
    callers (ui/components/chat.py's write_pipeline_step) don't need to change
    at all -- only how quickly and how often on_progress fires changes.
    Transparently falls back to poll_run_until_settled -- network error, older
    server without the endpoint, proxy that strips streaming responses, or the
    stream closing early without ever sending run_settled (httpx.TimeoutException
    is itself an httpx.HTTPError) -- so callers get graceful degradation without
    handling two code paths themselves.
    """
    try:
        accumulated_steps: list[str] = []
        for event in stream_run_events(client, run_id, timeout=timeout):
            event_type = event.get("type")
            if event_type == "node_update":
                accumulated_steps.append(event["step"])
                if on_progress is not None:
                    on_progress({"steps": list(accumulated_steps)})
            elif event_type == "run_settled":
                return event["run"]
        raise httpx.TimeoutException(
            f"Run {run_id} event stream ended without settling", request=None
        )
    except httpx.HTTPError:
        return poll_run_until_settled(
            client, run_id, timeout=timeout, interval=interval, on_progress=on_progress
        )


def continue_run(
    client: httpx.Client,
    run_id: str,
    *,
    message: str,
    poll: bool = True,
    timeout: float = DEFAULT_RUN_POLL_TIMEOUT,
    interval: float = DEFAULT_POLL_INTERVAL,
    on_progress: Callable[[dict[str, Any]], None] | None = None,
) -> dict[str, Any]:
    response = client.post(
        f"/runs/{run_id}/continue", json={"message": message}, headers=_request_headers()
    )
    response.raise_for_status()
    continued = response.json()
    if not poll:
        return continued
    if continued.get("status") != "running":
        return continued
    return stream_run_until_settled(
        client,
        run_id,
        timeout=timeout,
        interval=interval,
        on_progress=on_progress,
    )


def resume_run(
    client: httpx.Client,
    run_id: str,
    *,
    user_response: str | None = None,
    approval_status: str | None = None,
    decision_type: str | None = None,
    message: str | None = None,
    form_data: dict[str, Any] | None = None,
    poll: bool = True,
    timeout: float = DEFAULT_RUN_POLL_TIMEOUT,
    interval: float = DEFAULT_POLL_INTERVAL,
    on_progress: Callable[[dict[str, Any]], None] | None = None,
) -> dict[str, Any]:
    payload: dict[str, Any] = {}
    if form_data is not None:
        payload["form_data"] = form_data
    elif decision_type is not None:
        payload["decision_type"] = decision_type
        if message is not None:
            payload["message"] = message
    elif user_response is not None:
        payload["user_response"] = user_response
    else:
        raise ValueError("user_response, decision_type, or form_data is required")
    if approval_status is not None:
        payload["approval_status"] = approval_status
    response = client.post(f"/runs/{run_id}/resume", json=payload, headers=_request_headers())
    response.raise_for_status()
    resumed = response.json()
    if not poll:
        return resumed
    if resumed.get("status") != "running":
        return resumed
    return stream_run_until_settled(
        client,
        run_id,
        timeout=timeout,
        interval=interval,
        on_progress=on_progress,
    )
