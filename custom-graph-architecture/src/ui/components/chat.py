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
from html import escape
from itertools import chain
from time import perf_counter
from typing import Any

import httpx
import streamlit as st

from src.enums import StreamEventType
from src.ui import api_client, state
from src.ui.wording import ERROR_COPY, THINKING_LABEL, thought_for

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


def timeline_html(
    steps: list[str], *, running: bool, elapsed_seconds: float | None = None
) -> str:
    """Build the step timeline: a header, then one row per step the run has reached.

    Rendered whole on every update into a single placeholder, so a settled row keeps its
    checkmark without any DOM bookkeeping. Only the newest row is given the enter
    animation — the rest would replay their fade-in on every subsequent step.
    """
    header = THINKING_LABEL if running else thought_for(elapsed_seconds or 0)
    dot = "pt-timeline__header-dot"
    if running:
        dot += " pt-timeline__header-dot--active"

    rows = []
    newest = len(steps) - 1
    for index, label in enumerate(steps):
        if running and index == newest:
            icon = '<span class="pt-timeline__icon pt-timeline__icon--active"></span>'
        else:
            icon = '<span class="pt-timeline__icon pt-timeline__icon--done">✓</span>'
        enter = " pt-timeline__row--enter" if index == newest else ""
        rows.append(
            f'<div class="pt-timeline__row{enter}">{icon}'
            f'<span class="pt-timeline__text">{escape(label)}</span></div>'
        )

    return (
        '<div class="pt-timeline">'
        '<div class="pt-timeline__header">'
        f'<span class="{dot}"></span>'
        f'<span class="pt-timeline__header-text">{escape(header)}</span>'
        "</div>" + "".join(rows) + "</div>"
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
            # Only a turn taken in this browser session carries its steps; history
            # reloaded from the API is the conversation, not how it was produced.
            timeline = message.get("timeline")
            if timeline:
                st.markdown(timeline, unsafe_allow_html=True)
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


def send_turn(
    client: httpx.Client,
    session_id: str,
    text: str,
    form_data: dict[str, Any] | None = None,
) -> None:
    """Send one message and draw the turn: its steps as they happen, then its replies.

    The reply may be an answer, or the plan and its review question — both of which
    arrive as message frames, so this function does not need to know which branch ran.
    A run that stops to collect the profile also sends a form frame, which is held in
    session state for the next pass to render rather than drawn here.

    The user's own message is appended by the caller, which renders it before calling in
    so it is on screen for the length of the turn.
    """
    started = perf_counter()
    steps: list[str] = []
    parts: list[str] = []
    st.session_state.pending_form = None

    # Opened before the assistant bubble: a stream that turns out to be a 401 is retried
    # by ``with_session_retry``, and an empty bubble would already be on screen.
    opening = st.empty()
    opening.markdown(timeline_html(steps, running=True), unsafe_allow_html=True)
    try:
        frames = _open_chat_stream(client, session_id, text, form_data)
    except httpx.TimeoutException:
        opening.empty()
        _finish_failed_turn(parts, ERROR_COPY["chat_timeout"])
        return
    except (httpx.HTTPError, json.JSONDecodeError, KeyError) as exc:
        opening.empty()
        _finish_failed_turn(parts, f"⚠️ {ERROR_COPY['chat_failed']}: {_detail(exc)}")
        return
    opening.empty()

    with st.chat_message("assistant", avatar=_AVATARS["assistant"]):
        timeline = st.empty()
        body = st.empty()
        timeline.markdown(timeline_html(steps, running=True), unsafe_allow_html=True)

        failure: str | None = None
        try:
            _consume_stream(frames, steps, parts, timeline, body)
        except httpx.TimeoutException:
            failure = ERROR_COPY["chat_timeout"]
        except (httpx.HTTPError, json.JSONDecodeError, KeyError) as exc:
            failure = f"⚠️ {ERROR_COPY['chat_failed']}: {_detail(exc)}"

        if failure:
            parts.append(failure)
        settled = timeline_html(
            steps, running=False, elapsed_seconds=perf_counter() - started
        )
        timeline.markdown(settled, unsafe_allow_html=True)

        reply = _joined(parts) or _FALLBACK_REPLY
        body.markdown(reply)

    st.session_state.messages.append(
        {"role": "assistant", "content": reply, "timeline": settled}
    )
    if failure is None:
        _refresh_conversation_names(client)


def _joined(parts: list[str]) -> str:
    """Join a turn's replies into the one message the transcript keeps.

    Blank-line separated rather than concatenated: the frames are whole messages, and
    running them together turns a plan and the question about it into one paragraph.
    """
    return "\n\n".join(part for part in parts if part)


def _open_chat_stream(
    client: httpx.Client,
    session_id: str,
    text: str,
    form_data: dict[str, Any] | None = None,
) -> Iterator[dict[str, Any]]:
    """Start a streamed turn, reminting the session token once on 401.

    The first frame is pulled here because that is what makes the request happen: an
    expired token is a 401 on the response, not on building the generator.
    """

    def call(token: str) -> Iterator[dict[str, Any]]:
        stream = api_client.send_message_stream(client, token, text, form_data)
        first = next(stream, None)
        return stream if first is None else chain([first], stream)

    return with_session_retry(client, call, session_id=session_id)


def _consume_stream(
    frames: Iterator[dict[str, Any]],
    steps: list[str],
    parts: list[str],
    timeline: Any,
    body: Any,
) -> None:
    """Read one streamed turn, growing the timeline and the reply as frames arrive."""
    for frame in frames:
        if frame.get("type") == StreamEventType.STEP:
            label = frame.get("label")
            if label:
                steps.append(label)
                timeline.markdown(
                    timeline_html(steps, running=True), unsafe_allow_html=True
                )
            continue

        if frame.get("type") == StreamEventType.FORM:
            st.session_state.pending_form = frame.get("form")
            continue

        content = frame.get("content")
        if content:
            parts.append(content)
            body.markdown(_joined(parts))


def _finish_failed_turn(parts: list[str], error_text: str) -> None:
    """Keep any partial answer, then show the error as its own message."""
    if parts:
        st.session_state.messages.append(
            {"role": "assistant", "content": _joined(parts)}
        )
    st.session_state.messages.append({"role": "assistant", "content": error_text})
    with st.chat_message("assistant", avatar=_AVATARS["assistant"]):
        st.markdown(error_text)


def _refresh_conversation_names(client: httpx.Client) -> None:
    """Pull the sidebar's conversation list back in sync after a turn.

    Naming is the server's job (``src.services.session_naming``): the first turn
    claims the conversation, stores a placeholder cut from the message, then
    overwrites it with a summarised title a moment later. The client must not
    derive a label of its own — this runs after the turn, so a local guess would
    always win that race and the generated title would never be seen.

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
    "timeline_html",
    "with_session_retry",
]
