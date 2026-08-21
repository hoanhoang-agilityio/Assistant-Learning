"""Rendering the transcript, and sending one turn to the agent.

The transcript shown here is the one the API returned, not a client-side
reconstruction: history comes from ``GET /chatbot/messages`` (the LangGraph
checkpointer) and each reply comes from ``POST /chatbot/chat/stream``. Anything
the UI invented locally would drift from what the agent sees on the next turn,
and the confirm gate — which resumes from a checkpoint — would be answering
about a plan the user was never shown.
"""

from __future__ import annotations

import json
from collections.abc import Callable, Iterator
from typing import Any

import httpx
import streamlit as st

from app.ui import api_client, state
from app.ui.wording import ERROR_COPY, THINKING_LABEL

_AVATARS = {"user": "🙂", "assistant": "🏋️"}
_FALLBACK_REPLY = "I didn't manage to put a reply together. Try rephrasing that?"


def run_guarded_backend_action(
    action: Callable[[], Any],
    *,
    on_success: Callable[[Any], None],
    timeout_message: str,
    error_prefix: str,
    rerun_on_settle: bool = False,
) -> None:
    """Run a backend call, then either apply ``on_success`` or say what failed.

    Every button and form in this UI goes through here. A network error, an
    unparseable body or a 500 must end as an assistant message the user can read
    and act on — never as a raw traceback where the answer should have been.

    Args:
        action: The call to make. Its return value is passed to ``on_success``.
        on_success: What to do with a successful result.
        timeout_message: Shown verbatim when the request timed out. Written for
            the specific action, because "still working" and "nothing happened"
            need different follow-ups from the user.
        error_prefix: Prepended to the error detail on any other failure.
        rerun_on_settle: Rerun the script afterwards, for actions whose result
            changes what the sidebar or the input row should render.
    """
    try:
        result = action()
    except httpx.TimeoutException:
        st.session_state.messages.append({"role": "assistant", "content": timeout_message})
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
    """Extract the part of a failure worth showing the user.

    Args:
        exc: The exception that ended the call.

    Returns:
        The API's ``detail`` field when there is one — it is written for humans
        — and the exception's own text otherwise.
    """
    if isinstance(exc, httpx.HTTPStatusError):
        try:
            detail = exc.response.json().get("detail")
        except (json.JSONDecodeError, ValueError):
            detail = None
        if isinstance(detail, str):
            return detail
        return f"the server returned {exc.response.status_code}"
    return str(exc)


def with_session_retry(client: httpx.Client, call: Callable[[str], Any], *, session_id: str) -> Any:
    """Make a session-scoped call, re-minting the token once if it has expired.

    Session tokens are JWTs with the same lifetime as user tokens, and a user
    can sit in one conversation for longer than that. ``GET /auth/sessions``
    issues a fresh token per conversation, so one re-list turns a 401 into a
    successful retry instead of an unexplained failure mid-conversation.

    Args:
        client: An open API client.
        call: Takes a session token and makes the request.
        session_id: The conversation the token must be scoped to.

    Returns:
        Whatever ``call`` returns.

    Raises:
        httpx.HTTPStatusError: On a non-401 failure, or when the retry fails
            too.
        KeyError: When the conversation no longer exists after the re-list,
            which ``run_guarded_backend_action`` reports as a failed action.
    """
    token = _token_for(session_id)
    try:
        return call(token)
    except httpx.HTTPStatusError as exc:
        if exc.response.status_code != 401:
            raise
    state.sync_conversations(client)
    return call(_token_for(session_id))


def _token_for(session_id: str) -> str:
    """Look up the stored token for a conversation.

    Args:
        session_id: The conversation.

    Returns:
        Its session token.

    Raises:
        KeyError: When the conversation is not in the sidebar, which means it
            was deleted elsewhere.
    """
    for item in st.session_state.conversations:
        if item["session_id"] == session_id:
            return str(item["token"])
    raise KeyError("that conversation no longer exists")


def thinking_html(label: str = THINKING_LABEL) -> str:
    """Build the pulsing "Thinking…" row shown until the first token arrives.

    Subagent work (planning, review) emits no chat tokens, so this is a single
    honest indicator rather than a step-by-step timeline.

    Args:
        label: The text beside the dot.

    Returns:
        Markup using the shared ``.pt-timeline`` styles.
    """
    return (
        '<div class="pt-timeline">'
        '<div class="pt-timeline__header">'
        '<span class="pt-timeline__header-dot pt-timeline__header-dot--active"></span>'
        f'<span class="pt-timeline__header-text">{label}</span>'
        "</div></div>"
    )


def render_messages(messages: list[dict[str, Any]]) -> None:
    """Draw a transcript.

    Args:
        messages: Messages with ``role`` and ``content``, oldest first.
    """
    for message in messages:
        role = message["role"]
        # The graph stores system messages in the same thread; they are context
        # for the model, not part of the conversation the user had.
        if role == "system":
            continue
        with st.chat_message(role, avatar=_AVATARS.get(role)):
            st.markdown(message["content"])


def load_conversation(client: httpx.Client, session_id: str) -> None:
    """Open a conversation and pull its history from the database.

    Args:
        client: An open API client.
        session_id: The conversation to open.
    """

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
    """Send one message and stream the agent's reply into the chat window.

    The reply may be an answer, a request for the profile fields still missing,
    or the confirm gate's question — all of which arrive as text chunks, so this
    function does not need to know which branch ran.

    The user's own message is appended by the caller, which renders it before
    calling in so it is on screen for the length of the turn.

    Args:
        client: An open API client.
        session_id: The conversation to send into.
        text: The user's message.
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
    """Start a streamed turn, reminting the session token once on 401.

    The retry only happens if the first request failed before any chunk: a 401
    means the graph never started. Retrying after tokens have arrived would
    run the turn twice.

    Args:
        client: An open API client.
        session_id: The conversation the token must be scoped to.
        text: The user's message.

    Returns:
        The first text chunk and the rest of the stream. ``None`` and an
        exhausted iterator when the server closed without sending any content.
    """

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
    """Read one streamed turn into the chat window.

    Args:
        client: An open API client.
        session_id: The conversation to send into.
        text: The user's message.
        thinking: The placeholder showing ``Thinking…`` until the first chunk.
        chunks: Filled as tokens arrive, so a mid-stream failure can keep them.

    Returns:
        The concatenated reply, empty when the server sent no text.
    """
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
    """Keep any partial answer, then show the error as its own message.

    Args:
        chunks: Text already received when the stream failed. Empty when the
            failure happened before the first token.
        error_text: What to tell the user about the failure.
    """
    if chunks:
        st.session_state.messages.append({"role": "assistant", "content": "".join(chunks)})
    st.session_state.messages.append({"role": "assistant", "content": error_text})
    with st.chat_message("assistant", avatar=_AVATARS["assistant"]):
        st.markdown(error_text)


def _refresh_conversation_names(client: httpx.Client) -> None:
    """Pull the names the server gave the conversations into the sidebar.

    Naming is the server's job (``app.services.session_naming``): the first turn
    claims the session, writes a placeholder from the message, then overwrites it
    with an LLM-generated title a second or two later. The client must not derive
    a name of its own — doing so raced that background write and, because this
    runs after the turn, the client's guess always won.

    Failure is swallowed on purpose: a conversation whose label is one turn stale
    still works, and turning a cosmetic problem into an error message on a turn
    that just succeeded would be worse. The sidebar's refresh button and the next
    turn both try again.

    Args:
        client: An open API client.
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
