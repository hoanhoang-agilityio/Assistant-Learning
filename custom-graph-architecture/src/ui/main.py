"""Streamlit front end for the API.

Run it from the project root::

    uv run streamlit run src/ui/main.py

It is a client of ``src.main``, not part of it: everything it knows comes from
``/api/v1``, so the two can be deployed separately and the UI cannot reach
around the API to the database or the graph.

The script re-executes top to bottom on every interaction, which is why the
order below is the whole design: seed state, sign in or stop, resolve which
conversation is open, draw the sidebar, draw the transcript, then take input. A
conversation is created on the first message rather than on arrival, so opening
the app costs nothing.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import httpx
import streamlit as st

from src.ui import api_client, state
from src.ui.components.auth import render_auth_gate
from src.ui.components.chat import (
    load_conversation,
    render_messages,
    run_guarded_backend_action,
    send_turn,
)
from src.ui.components.sidebar import render_sidebar
from src.ui.components.welcome import render_welcome
from src.ui.wording import CHAT_PLACEHOLDER, ERROR_COPY

st.set_page_config(page_title="Coach AI", page_icon="🏋️", layout="wide")

_STYLES_PATH = Path(__file__).parent / "styles" / "style.css"


def inject_css() -> None:
    """Load the stylesheet into the page."""
    st.markdown(
        f"<style>{_STYLES_PATH.read_text(encoding='utf-8')}</style>",
        unsafe_allow_html=True,
    )


def _open_most_recent(client: httpx.Client) -> None:
    """Open the newest conversation when arriving without one.

    Skipped while the user is composing a new chat, which is the one case
    where an empty transcript is what was asked for.
    """
    if st.session_state.active_session_id is not None or st.session_state.composing_new:
        return
    conversations = st.session_state.conversations
    if not conversations:
        return
    load_conversation(client, conversations[0]["session_id"])


def _ensure_conversation(client: httpx.Client) -> str | None:
    """Return the conversation to send into, creating one if there is none.

    Deliberately does not clear the transcript the way opening a stored
    conversation does — the message that triggered the creation is about to be
    appended to it.
    """
    session_id = st.session_state.active_session_id
    if session_id is not None:
        return session_id

    created: dict[str, str] = {}

    def on_success(session: dict[str, Any]) -> None:
        state.add_conversation(session)
        st.session_state.active_session_id = session["session_id"]
        st.session_state.composing_new = False
        created["session_id"] = session["session_id"]

    run_guarded_backend_action(
        lambda: api_client.create_session(client, state.user_token(client)),
        on_success=on_success,
        timeout_message="⏳ Couldn't start a new conversation in time. Try again.",
        error_prefix=ERROR_COPY["new_chat_failed"],
    )
    return created.get("session_id")


def main() -> None:
    """Draw one pass of the app."""
    state.init()
    inject_css()

    with api_client.api_client() as client:
        if not state.signed_in():
            render_auth_gate(client)
            return

        # Before the sidebar, so it can mark the open conversation on this pass
        # rather than one interaction later.
        _open_most_recent(client)
        render_sidebar(client)

        messages: list[dict[str, Any]] = st.session_state.messages
        render_messages(messages)

        query = st.chat_input(CHAT_PLACEHOLDER)
        active_query = query or st.session_state.pending_query

        if not messages and not active_query:
            render_welcome()

        if not active_query:
            return

        st.session_state.pending_query = None
        session_id = _ensure_conversation(client)
        if session_id is not None:
            # Echo before sending: the turn blocks for as long as the graph
            # takes, and the user should see their own message during it rather
            # than a blank gap.
            st.session_state.messages.append({"role": "user", "content": active_query})
            render_messages([{"role": "user", "content": active_query}])
            send_turn(client, session_id, active_query)
        st.rerun()


main()
