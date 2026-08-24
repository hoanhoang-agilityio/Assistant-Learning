"""Rendering the transcript, and sending one turn to the graph.

The transcript shown here is the one the API returned, not a client-side
reconstruction: history comes from ``GET /messages`` (the LangGraph
checkpointer) and each reply comes from ``POST /chat/stream``. Anything the UI
invented locally would drift from what the graph sees on the next turn, and a
paused HITL or missing-info interrupt — which resumes from a checkpoint —
would be answering about a plan the user was never shown.
"""

from __future__ import annotations

import json
from collections.abc import Callable, Iterator
from typing import Any

import httpx
import streamlit as st

from src.ui import api_client, state
from src.ui.wording import ERROR_COPY, THINKING_LABEL

_AVATARS = {"user": "👤", "assistant": "🏋️"}
_FALLBACK_REPLY = "I didn't manage to put a reply together. Try rephrasing that?"
_EXPIRED_TOKEN_STATUS = 401


def run_guarded_backend_action(
    action: Callable[[], Any],
    *,
    on_success: Callable[[Any], None],
    timeout_message: str,
    error_prefix: str,
    rerun_on_settle: bool = False,
) -> None:
    """Run a backend call, then either apply ``on_success`` or say what failed."""
    try:
        result = action()
    except httpx.TimeoutException:
        st.session_state.messages.append(
            {"role": "assistant", "content": timeout_message}
        )
        if rerun_on_settle:
            st.rerun()
        return
    except (httpx.HTTPError, json.JSONDecodeError, KeyError) as exc:
        st.session_state.messages.append(
            {"role": "assistant", "content": f"⚠️ {error_prefix}: {_detail(exc)}"}
        )
        if rerun_on_settle:
            st.rerun()
        return
    on_success(result)
    if rerun_on_settle:
        st.rerun()


def _detail(exc: Exception) -> str:
    """Extract the part of a failure worth showing the user."""
    if isinstance(exc, httpx.HTTPStatusError):
        try:
            detail = exc.response.json().get("detail")
        except (json.JSONDecodeError, ValueError):
            detail = None
        if isinstance(detail, str):
            return detail
        return f"the server returned {exc.response.status_code}"
    return str(exc)


def with_session_retry(
    client: httpx.Client, call: Callable[[str], Any], *, session_id: str
) -> Any:
    """Make a session-scoped call, re-minting the token once if it has expired."""
    token = _token_for(session_id)
    try:
        return call(token)
    except httpx.HTTPStatusError as exc:
        if exc.response.status_code != _EXPIRED_TOKEN_STATUS:
            raise
    state.sync_conversations(client)
    return call(_token_for(session_id))


def _token_for(session_id: str) -> str:
    """Look up the stored token for a conversation."""
    for item in st.session_state.conversations:
        if item["session_id"] == session_id:
            return str(item["token"])
    raise KeyError("that conversation no longer exists")


def thinking_html(label: str = THINKING_LABEL) -> str:
    """Build the pulsing "Thinking…" row shown until the first token arrives."""
    return (
        '<div class="pt-timeline">'
        '<div class="pt-timeline__header">'
        '<span class="pt-timeline__header-dot pt-timeline__header-dot--active"></span>'
        f'<span class="pt-timeline__header-text">{label}</span>'
        "</div></div>"
    )


def render_messages(messages: list[dict[str, Any]]) -> None:
    """Draw a transcript, oldest first."""
    for message in messages:
        role = message["role"]
        # The graph stores system messages in the same thread; they are context
        # for the model, not part of the conversation the user had.
        if role == "system":
            continue
        with st.chat_message(role, avatar=_AVATARS.get(role)):
            st.markdown(message["content"])


def load_conversation(client: httpx.Client, session_id: str) -> None:
    """Open a conversation and pull its history from the database."""

    def do_load() -> list[dict[str, Any]]:
        return with_session_retry(
            client,
            lambda token: api_client.get_messages(client, token),
            session_id=session_id,
        )

    def on_success(messages: list[dict[str, Any]]) -> None:
        state.open_conversation(session_id, messages)

    run_guarded_backend_action(
        do_load,
        on_success=on_success,
        timeout_message="⏳ That conversation is taking a while to load. Try again in a moment.",
        error_prefix=ERROR_COPY["history_failed"],
    )


def send_turn(client: httpx.Client, session_id: str, text: str) -> None:
    """Send one message and stream the graph's reply into the chat window.

    The reply may be an answer, a request for the profile fields still missing,
    or the HITL review question — all of which arrive as text chunks, so this
    function does not need to know which branch ran.

    The user's own message is appended by the caller, which renders it before
    calling in so it is on screen for the length of the turn.
    """
    thinking = st.empty()
    thinking.markdown(thinking_html(), unsafe_allow_html=True)
    chunks: list[str] = []
    try:
        reply = _consume_stream(client, session_id, text, thinking, chunks)
    except httpx.TimeoutException:
        _finish_failed_turn(chunks, ERROR_COPY["chat_timeout"])
        return
    except (httpx.HTTPError, json.JSONDecodeError, KeyError) as exc:
        _finish_failed_turn(chunks, f"⚠️ {ERROR_COPY['chat_failed']}: {_detail(exc)}")
        return
    finally:
        thinking.empty()
    if not reply:
        reply = _FALLBACK_REPLY
        with st.chat_message("assistant", avatar=_AVATARS["assistant"]):
            st.markdown(reply)
    st.session_state.messages.append({"role": "assistant", "content": reply})
    _refresh_conversation_names(client)


def _open_chat_stream(
    client: httpx.Client, session_id: str, text: str
) -> tuple[str | None, Iterator[str]]:
    """Start a streamed turn, reminting the session token once on 401."""

    def call(token: str) -> tuple[str | None, Iterator[str]]:
        stream = api_client.send_message_stream(client, token, text)
        return next(stream, None), stream

    return with_session_retry(client, call, session_id=session_id)


def _consume_stream(
    client: httpx.Client,
    session_id: str,
    text: str,
    thinking: Any,
    chunks: list[str],
) -> str:
    """Read one streamed turn into the chat window."""
    first, rest = _open_chat_stream(client, session_id, text)
    if first is None:
        return ""
    thinking.empty()
    chunks.append(first)

    def tokens() -> Iterator[str]:
        yield first
        for chunk in rest:
            chunks.append(chunk)
            yield chunk

    with st.chat_message("assistant", avatar=_AVATARS["assistant"]):
        return str(st.write_stream(tokens()) or "")


def _finish_failed_turn(chunks: list[str], error_text: str) -> None:
    """Keep any partial answer, then show the error as its own message."""
    if chunks:
        st.session_state.messages.append(
            {"role": "assistant", "content": "".join(chunks)}
        )
    st.session_state.messages.append({"role": "assistant", "content": error_text})
    with st.chat_message("assistant", avatar=_AVATARS["assistant"]):
        st.markdown(error_text)


def _refresh_conversation_names(client: httpx.Client) -> None:
    """Pull the sidebar's conversation list back in sync after a turn.

    Failure is swallowed on purpose: a stale sidebar still works, and turning
    a cosmetic problem into an error message on a turn that just succeeded
    would be worse. The sidebar's refresh button and the next turn both try
    again.
    """
    try:
        state.sync_conversations(client)
    except (httpx.HTTPError, KeyError):
        return


__all__ = [
    "load_conversation",
    "render_messages",
    "run_guarded_backend_action",
    "send_turn",
    "thinking_html",
    "with_session_retry",
]
