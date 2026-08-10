"""Every HTTP call the Streamlit UI makes against the app API.

One module owns all of them so the token-scoping rule from ``app/api/v1/auth.py``
lives in exactly one place: the **user token** creates and lists conversations,
and a **session token** is the only thing that may read, rename, delete or talk
to one. Each function names in its signature which scope it expects, because
sending the wrong one is a 401 rather than something the UI could recover from.

Nothing here swallows an error. A failed call raises ``httpx.HTTPStatusError``
and the caller decides what the user sees — a client that returned an empty
result on failure would render as the assistant silently saying nothing.
"""

from __future__ import annotations

import os
from typing import Any

import httpx

DEFAULT_API_BASE_URL = "http://localhost:8000"
API_PREFIX = "/api/v1"

# A build_plan turn runs a planning subgraph, macro maths, three verifiers and a
# composer, so the ceiling is minutes rather than the usual seconds. Too low a
# timeout here does not cancel the work — the graph keeps running server-side
# and checkpoints — it only loses the answer.
CHAT_TIMEOUT = 300.0
DEFAULT_REQUEST_TIMEOUT = 30.0


def get_api_base_url() -> str:
    """Return the API origin the UI talks to.

    Returns:
        ``API_BASE_URL`` from the environment, or localhost, without a trailing
        slash.
    """
    return os.getenv("API_BASE_URL", DEFAULT_API_BASE_URL).rstrip("/")


def api_client() -> httpx.Client:
    """Open a client pointed at the versioned API surface.

    Returns:
        A client whose base URL already includes ``/api/v1``, so call sites read
        as the route paths they map to.
    """
    return httpx.Client(
        base_url=f"{get_api_base_url()}{API_PREFIX}",
        timeout=DEFAULT_REQUEST_TIMEOUT,
    )


def _bearer(token: str) -> dict[str, str]:
    """Build the Authorization header for a token.

    Args:
        token: A user- or session-scoped access token.

    Returns:
        The header dict.
    """
    return {"Authorization": f"Bearer {token}"}


def _json(response: httpx.Response) -> Any:
    """Raise on an error status, then decode the body.

    Args:
        response: The response to check.

    Returns:
        The decoded JSON body.

    Raises:
        httpx.HTTPStatusError: On any 4xx or 5xx.
    """
    response.raise_for_status()
    return response.json()


# ----------------------------------------------------------------------
# Authentication
# ----------------------------------------------------------------------


def register(
    client: httpx.Client, *, email: str, password: str, username: str | None = None
) -> dict[str, Any]:
    """Create an account.

    Args:
        client: An open API client.
        email: The account's email address.
        password: The chosen password.
        username: Optional display name.

    Returns:
        A ``UserResponse`` body: id, email, username, ``token`` and
        ``refresh_token``.

    Raises:
        httpx.HTTPStatusError: 409 when the email is taken, 422 when the
            password fails the strength rules.
    """
    payload: dict[str, Any] = {"email": email, "password": password}
    if username:
        payload["username"] = username
    return _json(client.post("/auth/register", json=payload))


def login(client: httpx.Client, *, email: str, password: str) -> dict[str, Any]:
    """Exchange credentials for a user token.

    Sent as form fields, not JSON: ``/auth/login`` declares ``Form(...)``
    parameters.

    Args:
        client: An open API client.
        email: The account's email address.
        password: The account's password.

    Returns:
        A ``TokenResponse`` body, including ``email`` and ``username`` when set.

    Raises:
        httpx.HTTPStatusError: 401 when the credentials do not match.
    """
    return _json(
        client.post(
            "/auth/login",
            data={"email": email, "password": password, "grant_type": "password"},
        )
    )


def refresh_tokens(client: httpx.Client, refresh_token: str) -> dict[str, Any]:
    """Rotate a refresh token for a fresh user token.

    Single-use server-side, so the returned ``refresh_token`` must replace the
    one that was sent — reusing the old value fails from here on.

    Args:
        client: An open API client.
        refresh_token: The stored refresh credential.

    Returns:
        A ``TokenResponse`` body carrying both new tokens.

    Raises:
        httpx.HTTPStatusError: 401 when the refresh token is spent or expired.
    """
    return _json(client.post("/auth/refresh", data={"refresh_token": refresh_token}))


def logout(client: httpx.Client, user_token: str) -> None:
    """Revoke the user token and every refresh token it belongs to.

    Args:
        client: An open API client.
        user_token: The user-scoped access token.

    Raises:
        httpx.HTTPStatusError: On any non-2xx other than a token already
            rejected, which the caller treats as already logged out.
    """
    client.post("/auth/logout", headers=_bearer(user_token)).raise_for_status()


# ----------------------------------------------------------------------
# Conversations
# ----------------------------------------------------------------------


def create_session(client: httpx.Client, user_token: str) -> dict[str, Any]:
    """Start a new conversation.

    Args:
        client: An open API client.
        user_token: The user-scoped access token.

    Returns:
        A ``SessionResponse``: ``session_id``, ``name`` (empty until the UI
        names it) and a session-scoped ``token``.

    Raises:
        httpx.HTTPStatusError: On any non-2xx.
    """
    return _json(client.post("/auth/session", headers=_bearer(user_token)))


def list_sessions(client: httpx.Client, user_token: str) -> list[dict[str, Any]]:
    """List the user's conversations, oldest first.

    Each entry carries a **freshly minted** session token, which is why this is
    also how the UI recovers from a session token that expired mid-visit.

    Args:
        client: An open API client.
        user_token: The user-scoped access token.

    Returns:
        The stored conversations in creation order.

    Raises:
        httpx.HTTPStatusError: 401 when the user token is no longer valid.
    """
    return _json(client.get("/auth/sessions", headers=_bearer(user_token)))


def rename_session(
    client: httpx.Client, session_token: str, session_id: str, name: str
) -> dict[str, Any]:
    """Rename a conversation.

    Args:
        client: An open API client.
        session_token: A token scoped to ``session_id``.
        session_id: The conversation to rename.
        name: The new name.

    Returns:
        The updated ``SessionResponse``.

    Raises:
        httpx.HTTPStatusError: 403 when the token is scoped to a different
            conversation.
    """
    return _json(
        client.patch(
            f"/auth/session/{session_id}/name",
            data={"name": name},
            headers=_bearer(session_token),
        )
    )


def delete_session(client: httpx.Client, session_token: str, session_id: str) -> None:
    """Delete a conversation.

    Args:
        client: An open API client.
        session_token: A token scoped to ``session_id``.
        session_id: The conversation to delete.

    Raises:
        httpx.HTTPStatusError: 403 when the token is scoped to a different
            conversation.
    """
    client.delete(f"/auth/session/{session_id}", headers=_bearer(session_token)).raise_for_status()


# ----------------------------------------------------------------------
# Chat
# ----------------------------------------------------------------------


def send_message(client: httpx.Client, session_token: str, text: str) -> list[dict[str, Any]]:
    """Send one turn and return what the agent replied.

    Only the new message is sent. The graph reads the rest of the conversation
    from its checkpointer, keyed by the session the token is scoped to, so
    replaying stored turns here would duplicate them.

    ``/chatbot/chat`` is used rather than ``/chatbot/chat/stream`` because a
    turn that stops at the confirm gate has no streamed answer to show: the
    question is produced by the interrupt, after the stream has ended. The
    non-streaming endpoint returns it as an ordinary message.

    Args:
        client: An open API client.
        session_token: A token scoped to the conversation.
        text: The user's message.

    Returns:
        The assistant messages produced this turn. Empty when the graph had
        nothing to say.

    Raises:
        httpx.HTTPStatusError: 401 when the session token expired, 500 when the
            turn failed server-side.
    """
    body = _json(
        client.post(
            "/chatbot/chat",
            json={"messages": [{"role": "user", "content": text}]},
            headers=_bearer(session_token),
            timeout=CHAT_TIMEOUT,
        )
    )
    return body["messages"]


def get_messages(client: httpx.Client, session_token: str) -> list[dict[str, Any]]:
    """Load a conversation's stored history.

    Read straight out of the LangGraph checkpointer, so this is what the agent
    itself will see on the next turn — not a client-side copy that can drift.

    Args:
        client: An open API client.
        session_token: A token scoped to the conversation.

    Returns:
        The stored messages, oldest first.

    Raises:
        httpx.HTTPStatusError: 401 when the session token expired.
    """
    body = _json(client.get("/chatbot/messages", headers=_bearer(session_token)))
    return body["messages"]


def clear_messages(client: httpx.Client, session_token: str) -> None:
    """Delete a conversation's stored history, keeping the conversation itself.

    Args:
        client: An open API client.
        session_token: A token scoped to the conversation.

    Raises:
        httpx.HTTPStatusError: On any non-2xx.
    """
    client.delete("/chatbot/messages", headers=_bearer(session_token)).raise_for_status()


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
]
