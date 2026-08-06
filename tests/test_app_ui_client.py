"""Tests for the Streamlit UI's API client and its error guard.

Two things are worth pinning down here, because both fail silently in a browser
rather than loudly in a test:

* **Token scope.** ``app/api/v1/auth.py`` accepts a user token on some routes
  and a session token on others. Sending the wrong one is a 401 the user reads
  as "the app is broken", so each request's ``Authorization`` header is asserted
  against the scope the route declares.
* **Failure handling.** Every button goes through ``run_guarded_backend_action``.
  A network error, an unparseable body or a 500 must end as a message in the
  transcript — never as a traceback where the answer should have been.

``st`` is patched at module level rather than driven through
``streamlit.testing``: the guard's whole contract is expressible in terms of
``session_state.messages`` and ``st.rerun()``, and no widget is involved.
"""

from __future__ import annotations

import json
from typing import Any
from unittest.mock import MagicMock, patch

import httpx
import pytest

from app.ui import api_client
from app.ui.components.chat import run_guarded_backend_action, with_session_retry
from app.ui.wording import conversation_title, name_from_message


@pytest.fixture
def session_state() -> MagicMock:
    """Minimal stand-in for ``st.session_state``, tracking only ``messages``."""
    state = MagicMock()
    state.messages = []
    return state


def _recording_client(handler: Any, requests: list[httpx.Request] | None = None) -> httpx.Client:
    """Build a client whose transport records and answers requests.

    Args:
        handler: Called with each request, returns the response.
        requests: Appended to, when given.

    Returns:
        A client pointed at the same base URL the real one uses.
    """

    def transport_handler(request: httpx.Request) -> httpx.Response:
        if requests is not None:
            requests.append(request)
        return handler(request)

    return httpx.Client(
        transport=httpx.MockTransport(transport_handler),
        base_url=f"http://testserver{api_client.API_PREFIX}",
    )


# ----------------------------------------------------------------------
# Token scope
# ----------------------------------------------------------------------


def test_login_posts_form_fields_not_json() -> None:
    """``/auth/login`` declares Form parameters; a JSON body is a 422."""
    requests: list[httpx.Request] = []
    client = _recording_client(
        lambda _: httpx.Response(
            200,
            json={
                "access_token": "user-token",
                "token_type": "bearer",
                "expires_at": "2026-08-06T12:00:00+00:00",
                "refresh_token": "refresh",
            },
        ),
        requests,
    )

    tokens = api_client.login(client, email="a@b.com", password="Str0ng!pass")

    assert tokens["access_token"] == "user-token"
    assert requests[0].headers["content-type"].startswith("application/x-www-form-urlencoded")
    assert b"grant_type=password" in requests[0].content


def test_session_routes_send_the_session_token() -> None:
    """Rename, delete and every chat route are scoped to one conversation."""
    requests: list[httpx.Request] = []
    client = _recording_client(
        lambda request: httpx.Response(
            200,
            json={"messages": []}
            if request.url.path.endswith("/messages")
            else {
                "session_id": "s-1",
                "name": "Cutting plan",
                "token": {
                    "access_token": "fresh",
                    "token_type": "bearer",
                    "expires_at": "2026-08-06T12:00:00+00:00",
                },
            },
        ),
        requests,
    )

    api_client.get_messages(client, "session-token")
    api_client.rename_session(client, "session-token", "s-1", "Cutting plan")

    assert [request.url.path for request in requests] == [
        "/api/v1/chatbot/messages",
        "/api/v1/auth/session/s-1/name",
    ]
    assert {request.headers["authorization"] for request in requests} == {"Bearer session-token"}


def test_list_sessions_sends_the_user_token() -> None:
    """Listing is a user-token route; a session token would be a 401."""
    requests: list[httpx.Request] = []
    client = _recording_client(lambda _: httpx.Response(200, json=[]), requests)

    api_client.list_sessions(client, "user-token")

    assert requests[0].headers["authorization"] == "Bearer user-token"
    assert requests[0].url.path == "/api/v1/auth/sessions"


def test_send_message_posts_only_the_new_turn() -> None:
    """Replaying stored turns would duplicate them against the checkpointer."""
    requests: list[httpx.Request] = []
    client = _recording_client(
        lambda _: httpx.Response(
            200, json={"messages": [{"role": "assistant", "content": "Here is your plan."}]}
        ),
        requests,
    )

    replies = api_client.send_message(client, "session-token", "build me a plan")

    assert replies == [{"role": "assistant", "content": "Here is your plan."}]
    assert json.loads(requests[0].content) == {
        "messages": [{"role": "user", "content": "build me a plan"}]
    }


def test_failed_call_raises_rather_than_returning_empty() -> None:
    """A client that swallowed this would render as the assistant saying nothing."""
    client = _recording_client(lambda _: httpx.Response(500, json={"detail": "boom"}))

    with pytest.raises(httpx.HTTPStatusError):
        api_client.get_messages(client, "session-token")


# ----------------------------------------------------------------------
# Expired session tokens
# ----------------------------------------------------------------------


@patch("app.ui.components.chat.state")
@patch("app.ui.components.chat.st")
def test_with_session_retry_remints_the_token_after_a_401(
    mock_st: MagicMock, mock_state: MagicMock
) -> None:
    """A session token can expire mid-conversation; re-listing issues a new one."""
    mock_st.session_state.conversations = [{"session_id": "s-1", "token": "stale"}]
    request = httpx.Request("GET", "http://testserver/api/v1/chatbot/messages")
    attempts: list[str] = []

    def sync(_client: Any) -> None:
        mock_st.session_state.conversations = [{"session_id": "s-1", "token": "fresh"}]

    mock_state.sync_conversations.side_effect = sync

    def call(token: str) -> str:
        attempts.append(token)
        if token == "stale":
            raise httpx.HTTPStatusError(
                "expired", request=request, response=httpx.Response(401, request=request)
            )
        return "ok"

    assert with_session_retry(MagicMock(), call, session_id="s-1") == "ok"
    assert attempts == ["stale", "fresh"]


@patch("app.ui.components.chat.state")
@patch("app.ui.components.chat.st")
def test_with_session_retry_does_not_retry_other_failures(
    mock_st: MagicMock, mock_state: MagicMock
) -> None:
    """A 500 is not an authentication problem, and retrying would send the turn twice."""
    mock_st.session_state.conversations = [{"session_id": "s-1", "token": "good"}]
    request = httpx.Request("POST", "http://testserver/api/v1/chatbot/chat")
    attempts: list[str] = []

    def call(token: str) -> str:
        attempts.append(token)
        raise httpx.HTTPStatusError(
            "boom", request=request, response=httpx.Response(500, request=request)
        )

    with pytest.raises(httpx.HTTPStatusError):
        with_session_retry(MagicMock(), call, session_id="s-1")

    assert attempts == ["good"]
    mock_state.sync_conversations.assert_not_called()


@patch("app.ui.components.chat.state")
@patch("app.ui.components.chat.st")
def test_with_session_retry_reports_a_conversation_that_vanished(
    mock_st: MagicMock, _mock_state: MagicMock
) -> None:
    """Deleted elsewhere: the guard turns the KeyError into a readable message."""
    mock_st.session_state.conversations = []

    with pytest.raises(KeyError):
        with_session_retry(MagicMock(), lambda _token: "unreachable", session_id="s-1")


# ----------------------------------------------------------------------
# The error guard
# ----------------------------------------------------------------------


@patch("app.ui.components.chat.st")
def test_calls_on_success_when_action_succeeds(
    mock_st: MagicMock, session_state: MagicMock
) -> None:
    mock_st.session_state = session_state
    on_success = MagicMock()

    run_guarded_backend_action(
        lambda: {"messages": []},
        on_success=on_success,
        timeout_message="timeout",
        error_prefix="error",
    )

    on_success.assert_called_once_with({"messages": []})
    assert session_state.messages == []
    mock_st.rerun.assert_not_called()


@patch("app.ui.components.chat.st")
def test_catches_network_timeout(mock_st: MagicMock, session_state: MagicMock) -> None:
    mock_st.session_state = session_state
    on_success = MagicMock()

    def action() -> dict:
        raise httpx.TimeoutException("timed out")

    run_guarded_backend_action(
        action,
        on_success=on_success,
        timeout_message="⏳ still working, please wait…",
        error_prefix="error",
    )

    on_success.assert_not_called()
    assert session_state.messages == [
        {"role": "assistant", "content": "⏳ still working, please wait…"}
    ]


@patch("app.ui.components.chat.st")
def test_catches_network_connection_error(mock_st: MagicMock, session_state: MagicMock) -> None:
    """Connection refused and DNS failures are ``httpx.HTTPError`` too."""
    mock_st.session_state = session_state

    def action() -> dict:
        raise httpx.ConnectError("connection refused")

    run_guarded_backend_action(
        action,
        on_success=MagicMock(),
        timeout_message="timeout",
        error_prefix="Couldn't get an answer",
    )

    assert len(session_state.messages) == 1
    assert session_state.messages[0]["role"] == "assistant"
    assert "Couldn't get an answer" in session_state.messages[0]["content"]


@patch("app.ui.components.chat.st")
def test_shows_the_api_detail_on_a_backend_failure(
    mock_st: MagicMock, session_state: MagicMock
) -> None:
    """The API's ``detail`` is written for humans; the status code is not."""
    mock_st.session_state = session_state
    request = httpx.Request("POST", "http://testserver/api/v1/chatbot/chat")
    response = httpx.Response(
        500, json={"detail": "Failed to process chat request"}, request=request
    )

    def action() -> dict:
        raise httpx.HTTPStatusError("server error", request=request, response=response)

    run_guarded_backend_action(
        action,
        on_success=MagicMock(),
        timeout_message="timeout",
        error_prefix="Couldn't get an answer",
    )

    assert "Failed to process chat request" in session_state.messages[0]["content"]


@patch("app.ui.components.chat.st")
def test_catches_malformed_json_response(mock_st: MagicMock, session_state: MagicMock) -> None:
    """A non-JSON body must not crash the script with the action unacknowledged."""
    mock_st.session_state = session_state

    def action() -> dict:
        raise json.JSONDecodeError("Expecting value", "not json", 0)

    run_guarded_backend_action(
        action,
        on_success=MagicMock(),
        timeout_message="timeout",
        error_prefix="Couldn't rename this conversation",
    )

    assert len(session_state.messages) == 1
    assert "Couldn't rename this conversation" in session_state.messages[0]["content"]


@patch("app.ui.components.chat.st")
def test_catches_missing_expected_key_in_response(
    mock_st: MagicMock, session_state: MagicMock
) -> None:
    """A well-formed but unexpectedly-shaped response is a backend failure too."""
    mock_st.session_state = session_state

    def action() -> dict:
        payload: dict = {}
        return {"session_id": payload["session_id"]}

    run_guarded_backend_action(
        action,
        on_success=MagicMock(),
        timeout_message="timeout",
        error_prefix="Couldn't start a new conversation",
    )

    assert len(session_state.messages) == 1
    assert "Couldn't start a new conversation" in session_state.messages[0]["content"]


@patch("app.ui.components.chat.st")
def test_reruns_on_success_when_requested(mock_st: MagicMock, session_state: MagicMock) -> None:
    mock_st.session_state = session_state

    run_guarded_backend_action(
        lambda: {"session_id": "s-1"},
        on_success=MagicMock(),
        timeout_message="timeout",
        error_prefix="error",
        rerun_on_settle=True,
    )

    mock_st.rerun.assert_called_once()


@patch("app.ui.components.chat.st")
def test_reruns_on_failure_when_requested(mock_st: MagicMock, session_state: MagicMock) -> None:
    """Button call sites need the error on screen now, not after the next click."""
    mock_st.session_state = session_state

    def action() -> dict:
        raise httpx.ConnectError("down")

    run_guarded_backend_action(
        action,
        on_success=MagicMock(),
        timeout_message="timeout",
        error_prefix="error",
        rerun_on_settle=True,
    )

    mock_st.rerun.assert_called_once()


# ----------------------------------------------------------------------
# Sidebar labels
# ----------------------------------------------------------------------


def test_unnamed_conversation_falls_back_to_a_placeholder() -> None:
    """``POST /auth/session`` creates conversations with an empty name."""
    assert conversation_title("", "New chat") == "New chat"


def test_conversation_title_is_truncated_to_one_line() -> None:
    title = conversation_title("a" * 80, "New chat")

    assert len(title) == 40
    assert title.endswith("…")


def test_name_from_message_collapses_whitespace() -> None:
    """A pasted plan arrives full of newlines; the sidebar row is one line."""
    assert name_from_message("build me\n  a  plan\n") == "build me a plan"
