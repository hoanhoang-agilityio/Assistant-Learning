"""Every HTTP call the Streamlit UI makes against the API.

One module owns all of them so the token-scoping rule from ``src/api/v1/auth.py``
lives in exactly one place: the **user token** creates and lists conversations,
and a **session token** is the only thing that may read, rename, delete or talk
to one.

Nothing here swallows an error. A failed call raises ``httpx.HTTPStatusError``
and the caller decides what the user sees.
"""

from __future__ import annotations

import json
import os
from collections.abc import Iterator
from typing import Any

import httpx

DEFAULT_API_BASE_URL = "http://localhost:8000"
API_PREFIX = "/api/v1"

# The coach agent can run a planning subgraph, macro maths and multiple
# verification passes in one turn, so the ceiling is minutes rather than the
# usual seconds. Too low a timeout here does not cancel the work — the graph
# keeps running server-side and checkpoints — it only loses the answer.
CHAT_TIMEOUT = 300.0
DEFAULT_REQUEST_TIMEOUT = 30.0


def get_api_base_url() -> str:
    """Return the API origin the UI talks to."""
    return os.getenv("API_BASE_URL", DEFAULT_API_BASE_URL).rstrip("/")


def api_client() -> httpx.Client:
    """Open a client pointed at the versioned API surface."""
    return httpx.Client(
        base_url=f"{get_api_base_url()}{API_PREFIX}",
        timeout=DEFAULT_REQUEST_TIMEOUT,
    )


def _bearer(token: str) -> dict[str, str]:
    """Build the Authorization header for a token."""
    return {"Authorization": f"Bearer {token}"}


def _json(response: httpx.Response) -> Any:
    """Raise on an error status, then decode the body."""
    response.raise_for_status()
    return response.json()


# ----------------------------------------------------------------------
# Authentication
# ----------------------------------------------------------------------


def register(
    client: httpx.Client, *, email: str, password: str, username: str | None = None
) -> dict[str, Any]:
    """Create an account."""
    payload: dict[str, Any] = {"email": email, "password": password}
    if username:
        payload["username"] = username
    return _json(client.post("/auth/register", json=payload))


def login(client: httpx.Client, *, email: str, password: str) -> dict[str, Any]:
    """Exchange credentials for a user token."""
    return _json(
        client.post(
            "/auth/login",
            data={"email": email, "password": password, "grant_type": "password"},
        )
    )


def refresh_tokens(client: httpx.Client, refresh_token: str) -> dict[str, Any]:
    """Rotate a refresh token for a fresh user token."""
    return _json(client.post("/auth/refresh", data={"refresh_token": refresh_token}))


def logout(client: httpx.Client, user_token: str) -> None:
    """Revoke the user token and every refresh token it belongs to."""
    client.post("/auth/logout", headers=_bearer(user_token)).raise_for_status()


# ----------------------------------------------------------------------
# Conversations
# ----------------------------------------------------------------------


def create_session(client: httpx.Client, user_token: str) -> dict[str, Any]:
    """Start a new conversation."""
    return _json(client.post("/auth/session", headers=_bearer(user_token)))


def list_sessions(client: httpx.Client, user_token: str) -> list[dict[str, Any]]:
    """List the user's conversations, oldest first."""
    return _json(client.get("/auth/sessions", headers=_bearer(user_token)))


def rename_session(
    client: httpx.Client, session_token: str, session_id: str, name: str
) -> dict[str, Any]:
    """Rename a conversation."""
    return _json(
        client.patch(
            f"/auth/session/{session_id}/name",
            data={"name": name},
            headers=_bearer(session_token),
        )
    )


def delete_session(client: httpx.Client, session_token: str, session_id: str) -> None:
    """Delete a conversation."""
    client.delete(
        f"/auth/session/{session_id}", headers=_bearer(session_token)
    ).raise_for_status()


# ----------------------------------------------------------------------
# Chat
# ----------------------------------------------------------------------


def send_message(
    client: httpx.Client, session_token: str, text: str
) -> list[dict[str, Any]]:
    """Send one turn and return what the graph replied.

    Only the new message is sent. The graph reads the rest of the conversation
    from its checkpointer, keyed by the session the token is scoped to.
    """
    body = _json(
        client.post(
            "/chat",
            json={"messages": [{"role": "user", "content": text}]},
            headers=_bearer(session_token),
            timeout=CHAT_TIMEOUT,
        )
    )
    return body["messages"]


def send_message_stream(
    client: httpx.Client,
    session_token: str,
    text: str,
    form_data: dict[str, Any] | None = None,
) -> Iterator[dict[str, Any]]:
    """Send one turn and yield the frames it produces, in order.

    Same payload as ``send_message``: only the new user message, plus the filled-in
    fields when this turn is answering a form. A ``step`` frame names a node the run has
    reached, a ``message`` frame carries one complete reply, a ``form`` frame carries
    fields the run is now waiting on, and the last frame is ``done``. If the run parks on
    a HITL interrupt, the question it is asking is the last message frame.
    """
    with client.stream(
        "POST",
        "/chat/stream",
        json={
            "messages": [{"role": "user", "content": text}],
            "form_data": form_data,
        },
        headers=_bearer(session_token),
        timeout=CHAT_TIMEOUT,
    ) as response:
        if response.is_error:
            response.read()
        response.raise_for_status()
        yield from _iter_sse_frames(response)


def _iter_sse_frames(response: httpx.Response) -> Iterator[dict[str, Any]]:
    """Yield decoded frames from an SSE body until a ``done`` frame, inclusive."""
    for line in response.iter_lines():
        if not line.startswith("data:"):
            continue
        payload = json.loads(line[5:].strip())
        yield payload
        if payload.get("done"):
            return


def get_messages(client: httpx.Client, session_token: str) -> list[dict[str, Any]]:
    """Load a conversation's stored history."""
    body = _json(client.get("/messages", headers=_bearer(session_token)))
    return body["messages"]


def clear_messages(client: httpx.Client, session_token: str) -> None:
    """Delete a conversation's stored history, keeping the conversation itself."""
    client.delete("/messages", headers=_bearer(session_token)).raise_for_status()


__all__ = [
    "API_PREFIX",
    "CHAT_TIMEOUT",
    "DEFAULT_API_BASE_URL",
    "DEFAULT_REQUEST_TIMEOUT",
    "api_client",
    "clear_messages",
    "create_session",
    "delete_session",
    "get_api_base_url",
    "get_messages",
    "list_sessions",
    "login",
    "logout",
    "refresh_tokens",
    "register",
    "rename_session",
    "send_message",
    "send_message_stream",
]
