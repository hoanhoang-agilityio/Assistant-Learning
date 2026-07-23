from __future__ import annotations

import os
import time
from collections.abc import Callable
from typing import Any

import httpx

DEFAULT_API_BASE_URL = "http://localhost:8000"
DEFAULT_REQUEST_TIMEOUT = 30.0
DEFAULT_POLL_INTERVAL = 2.0
DEFAULT_RUN_POLL_TIMEOUT = 900.0


def get_api_base_url() -> str:
    return os.getenv("API_BASE_URL", DEFAULT_API_BASE_URL).rstrip("/")


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
    )
    response.raise_for_status()
    return response.json()


def get_run(client: httpx.Client, run_id: str) -> dict[str, Any]:
    response = client.get(f"/runs/{run_id}")
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
    response = client.post(f"/runs/{run_id}/continue", json={"message": message})
    response.raise_for_status()
    continued = response.json()
    if not poll:
        return continued
    if continued.get("status") != "running":
        return continued
    return poll_run_until_settled(
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
    response = client.post(f"/runs/{run_id}/resume", json=payload)
    response.raise_for_status()
    resumed = response.json()
    if not poll:
        return resumed
    if resumed.get("status") != "running":
        return resumed
    return poll_run_until_settled(
        client,
        run_id,
        timeout=timeout,
        interval=interval,
        on_progress=on_progress,
    )
