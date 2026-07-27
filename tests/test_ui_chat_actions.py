"""Tests for run_guarded_backend_action (PR9).

The shared backend-action pattern extracted from chat.py's already-correct
_handle_plan_change/_handle_clarification, and applied (per PR9's scope) to
render_hitl_actions (approve/reject) and render_profile_form (profile
submission) -- previously the two most consequential user actions in the
app, with zero exception handling of their own.

st is patched at the module level (ui.components.chat.st) rather than using
the full streamlit.testing.v1.AppTest harness, since run_guarded_backend_action's
entire contract is expressible in terms of session_state.messages and
st.rerun() -- no widget rendering is involved. No new test framework or
dependency is introduced.
"""

from __future__ import annotations

import json
from unittest.mock import MagicMock, patch

import httpx
import pytest

from ui.components.chat import run_guarded_backend_action


@pytest.fixture
def session_state() -> MagicMock:
    """Minimal stand-in for st.session_state, tracking only `messages`."""
    state = MagicMock()
    state.messages = []
    return state


@patch("ui.components.chat.st")
def test_calls_on_success_when_action_succeeds(
    mock_st: MagicMock, session_state: MagicMock
) -> None:
    mock_st.session_state = session_state
    on_success = MagicMock()

    run_guarded_backend_action(
        lambda: {"status": "waiting_hitl"},
        on_success=on_success,
        timeout_message="timeout",
        error_prefix="error",
    )

    on_success.assert_called_once_with({"status": "waiting_hitl"})
    assert session_state.messages == []
    mock_st.rerun.assert_not_called()


@patch("ui.components.chat.st")
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


@patch("ui.components.chat.st")
def test_catches_network_connection_error(mock_st: MagicMock, session_state: MagicMock) -> None:
    """Regression (PR9): a network error other than a timeout (connection
    refused, DNS failure, etc.) must be caught too -- httpx.ConnectError is a
    subclass of httpx.HTTPError, the broader network/backend-failure clause."""
    mock_st.session_state = session_state

    def action() -> dict:
        raise httpx.ConnectError("connection refused")

    run_guarded_backend_action(
        action,
        on_success=MagicMock(),
        timeout_message="timeout",
        error_prefix="Couldn't save your approval",
    )

    assert len(session_state.messages) == 1
    assert session_state.messages[0]["role"] == "assistant"
    assert "Couldn't save your approval" in session_state.messages[0]["content"]


@patch("ui.components.chat.st")
def test_catches_backend_failure_status(mock_st: MagicMock, session_state: MagicMock) -> None:
    """A non-2xx backend response (raise_for_status() inside api_client.py)
    must be caught as a backend failure, not crash the script."""
    mock_st.session_state = session_state
    request = httpx.Request("POST", "http://testserver/runs/run-1/resume")
    response = httpx.Response(500, request=request)

    def action() -> dict:
        raise httpx.HTTPStatusError("server error", request=request, response=response)

    run_guarded_backend_action(
        action,
        on_success=MagicMock(),
        timeout_message="timeout",
        error_prefix="Couldn't save your approval",
    )

    assert len(session_state.messages) == 1
    assert "Couldn't save your approval" in session_state.messages[0]["content"]


@patch("ui.components.chat.st")
def test_catches_malformed_json_response(mock_st: MagicMock, session_state: MagicMock) -> None:
    """Regression (PR9): a malformed/non-JSON backend response
    (json.JSONDecodeError, e.g. from response.json() inside api_client.py)
    must be caught -- the original bug this closes let exactly this crash the
    whole script with the user's action silently unacknowledged."""
    mock_st.session_state = session_state

    def action() -> dict:
        raise json.JSONDecodeError("Expecting value", "not json", 0)

    run_guarded_backend_action(
        action,
        on_success=MagicMock(),
        timeout_message="timeout",
        error_prefix="Couldn't save your profile details",
    )

    assert len(session_state.messages) == 1
    assert "Couldn't save your profile details" in session_state.messages[0]["content"]


@patch("ui.components.chat.st")
def test_catches_missing_expected_key_in_response(
    mock_st: MagicMock, session_state: MagicMock
) -> None:
    """Regression (PR9): a well-formed but unexpectedly-shaped response
    (missing a key the caller expects, e.g. created["run_id"]) must be caught
    as a backend failure, not crash the script."""
    mock_st.session_state = session_state

    def action() -> dict:
        payload: dict = {}
        return {"run_id": payload["run_id"]}

    run_guarded_backend_action(
        action,
        on_success=MagicMock(),
        timeout_message="timeout",
        error_prefix="Couldn't save",
    )

    assert len(session_state.messages) == 1
    assert "Couldn't save" in session_state.messages[0]["content"]


@patch("ui.components.chat.st")
def test_reruns_on_success_when_requested(mock_st: MagicMock, session_state: MagicMock) -> None:
    mock_st.session_state = session_state

    run_guarded_backend_action(
        lambda: {"status": "completed"},
        on_success=MagicMock(),
        timeout_message="timeout",
        error_prefix="error",
        rerun_on_settle=True,
    )

    mock_st.rerun.assert_called_once()


@patch("ui.components.chat.st")
def test_reruns_on_failure_when_requested(mock_st: MagicMock, session_state: MagicMock) -> None:
    """The button/form-triggered call sites (approve/reject/profile submission)
    need an immediate rerun on failure too, so the user sees the error message
    right away rather than only after some later, unrelated interaction."""
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


@patch("ui.components.chat.st")
def test_does_not_rerun_by_default(mock_st: MagicMock, session_state: MagicMock) -> None:
    """Preserve existing behavior for _handle_plan_change/_handle_clarification,
    which never called st.rerun() -- rerun_on_settle defaults to False."""
    mock_st.session_state = session_state

    run_guarded_backend_action(
        lambda: {"status": "completed"},
        on_success=MagicMock(),
        timeout_message="timeout",
        error_prefix="error",
    )

    mock_st.rerun.assert_not_called()
