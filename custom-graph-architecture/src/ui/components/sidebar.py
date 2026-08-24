"""The conversation sidebar, backed by the database rather than by memory.

Every row here comes from ``GET /auth/sessions``, and opening one reads its
messages from the checkpointer. Nothing about the list is reconstructed from
what happened in this browser session, which is what makes a conversation
started on another device show up here, and a rename made here survive a
reload.

Rename and delete send the **session** token, not the user token: ``auth.py``
scopes those two routes to the conversation being changed, so the sidebar keeps
one token per row rather than a single token for the account.
"""

from __future__ import annotations

from typing import Any

import httpx
import streamlit as st

from src.ui import api_client, state
from src.ui.components.chat import (
    load_conversation,
    run_guarded_backend_action,
    with_session_retry,
)
from src.ui.wording import (
    ERROR_COPY,
    NEW_CONVERSATION_NAME,
    TAGLINE,
    conversation_title,
)


def _render_conversation_list(client: httpx.Client) -> None:
    """Draw one row per stored conversation, newest first."""
    conversations: list[dict[str, Any]] = st.session_state.conversations
    if not conversations:
        st.markdown(
            '<p class="pt-sidebar__label">No conversations yet — start one above.</p>',
            unsafe_allow_html=True,
        )
        return

    st.markdown(
        '<div class="pt-sidebar__section"><p class="pt-sidebar__label">Recent</p></div>',
        unsafe_allow_html=True,
    )

    active_id = st.session_state.active_session_id
    for item in conversations:
        session_id = item["session_id"]
        if session_id == active_id:
            # Marker read by style.css to give the open conversation the same
            # background as the hover state.
            st.markdown(
                '<div class="pt-active-conv-marker"></div>', unsafe_allow_html=True
            )
        if st.button(
            conversation_title(item["name"], NEW_CONVERSATION_NAME),
            key=f"conversation_{session_id}",
            use_container_width=True,
        ):
            load_conversation(client, session_id)
            st.rerun()


def _render_conversation_actions(
    client: httpx.Client, conversation: dict[str, Any]
) -> None:
    """Draw rename, clear and delete for the open conversation."""
    session_id = conversation["session_id"]
    st.markdown("---")

    with st.popover("✏️ Rename", use_container_width=True):
        name = st.text_input(
            "Conversation name",
            value=conversation["name"],
            max_chars=100,
            key=f"rename_input_{session_id}",
        )
        if st.button("Save", type="primary", key=f"rename_save_{session_id}"):
            _rename(client, session_id, name)

    columns = st.columns(2)
    if columns[0].button(
        "🧹 Clear", use_container_width=True, key=f"clear_{session_id}"
    ):
        _clear(client, session_id)
    if columns[1].button(
        "🗑 Delete", use_container_width=True, key=f"delete_{session_id}"
    ):
        _delete(client, session_id)


def _rename(client: httpx.Client, session_id: str, name: str) -> None:
    """Rename a conversation."""

    def do_rename() -> dict[str, Any]:
        return with_session_retry(
            client,
            lambda token: api_client.rename_session(client, token, session_id, name),
            session_id=session_id,
        )

    def on_success(session: dict[str, Any]) -> None:
        # The API sanitizes the name, so the sidebar takes what was stored
        # rather than what was typed.
        state.set_conversation_name(session_id, session.get("name") or "")

    run_guarded_backend_action(
        do_rename,
        on_success=on_success,
        timeout_message="⏳ The rename didn't go through in time. Try again.",
        error_prefix=ERROR_COPY["rename_failed"],
        rerun_on_settle=True,
    )


def _clear(client: httpx.Client, session_id: str) -> None:
    """Delete a conversation's history, keeping the conversation itself.

    Clears the checkpoint rows, which means the plan and profile the graph was
    holding for this thread go too — the conversation restarts from nothing.
    """

    def do_clear() -> None:
        return with_session_retry(
            client,
            lambda token: api_client.clear_messages(client, token),
            session_id=session_id,
        )

    def on_success(_: None) -> None:
        st.session_state.messages = []

    run_guarded_backend_action(
        do_clear,
        on_success=on_success,
        timeout_message="⏳ Clearing didn't finish in time. Try again.",
        error_prefix=ERROR_COPY["clear_failed"],
        rerun_on_settle=True,
    )


def _delete(client: httpx.Client, session_id: str) -> None:
    """Delete a conversation."""

    def do_delete() -> None:
        return with_session_retry(
            client,
            lambda token: api_client.delete_session(client, token, session_id),
            session_id=session_id,
        )

    def on_success(_: None) -> None:
        state.remove_conversation(session_id)

    run_guarded_backend_action(
        do_delete,
        on_success=on_success,
        timeout_message="⏳ The delete didn't go through in time. Try again.",
        error_prefix=ERROR_COPY["delete_failed"],
        rerun_on_settle=True,
    )


def _refresh(client: httpx.Client) -> None:
    """Re-read the conversation list from the database."""
    run_guarded_backend_action(
        lambda: state.sync_conversations(client),
        on_success=lambda _: None,
        timeout_message="⏳ Couldn't reach the server. Try again.",
        error_prefix=ERROR_COPY["sync_failed"],
        rerun_on_settle=True,
    )


def _sign_out(client: httpx.Client) -> None:
    """Revoke this session's tokens and return to the sign-in gate.

    The local state is cleared even when the revoke call fails: a user who
    clicked "sign out" must not be left signed in because the network was down.
    """
    auth = st.session_state.auth
    if auth is not None:
        try:
            api_client.logout(client, auth["access_token"])
        except httpx.HTTPError:
            pass
    state.sign_out()
    st.rerun()


def render_sidebar(client: httpx.Client) -> None:
    """Draw the whole sidebar."""
    with st.sidebar:
        st.markdown(
            '<div class="sidebar-brand">🏋️ Coach AI</div>', unsafe_allow_html=True
        )
        st.markdown(
            f'<p class="pt-sidebar__tagline">{TAGLINE}</p>',
            unsafe_allow_html=True,
        )

        if st.button(
            "➕ New chat", type="primary", use_container_width=True, key="new_chat"
        ):
            state.start_new_conversation()
            st.rerun()

        _render_conversation_list(client)

        conversation = state.active_conversation()
        if conversation is not None:
            _render_conversation_actions(client, conversation)

        st.markdown("---")
        auth = st.session_state.auth or {}
        st.markdown(
            f'<p class="pt-sidebar__label">Signed in as {auth.get("username") or auth.get("email", "")}</p>',
            unsafe_allow_html=True,
        )
        footer = st.columns(2)
        if footer[0].button(
            "🔄 Refresh", use_container_width=True, key="refresh_conversations"
        ):
            _refresh(client)
        if footer[1].button("↩ Sign out", use_container_width=True, key="sign_out"):
            _sign_out(client)


__all__ = ["render_sidebar"]
