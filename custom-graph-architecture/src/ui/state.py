"""What survives a Streamlit rerun: who is signed in, and which conversation is open.

Streamlit re-executes the whole script on every interaction, so anything that
must outlive a click lives in ``st.session_state``.

Tokens are held here and nowhere else. Not in the URL query string and not on
disk. The cost of that choice is visible and deliberate: a full page reload
starts a new Streamlit session and the user signs in again. The conversations
themselves are never lost, because they live in Postgres and are re-listed on
the next sign-in.

The user token is refreshed here rather than at the call sites, because the
refresh token is single-use: two call sites each rotating it would spend the
same credential twice and log the user out.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Any

import httpx
import streamlit as st

from src.ui import api_client

# Refresh this far ahead of expiry. A turn can run for minutes, so a token that
# is merely "still valid now" is not good enough — it has to outlive the request
# it is about to authorize.
_REFRESH_MARGIN = timedelta(minutes=10)


def init() -> None:
    """Seed every key the UI reads, so no component has to guard for absence."""
    defaults: dict[str, Any] = {
        "auth": None,
        "conversations": [],
        "active_session_id": None,
        "messages": [],
        "pending_query": None,
        "is_processing": False,
        "auth_error": None,
        # "New chat" is a local state, not a row in the database. The session is
        # created on the first message instead, so a user who opens the app,
        # clicks New chat and leaves does not leave an empty unnamed
        # conversation behind for every visit.
        "composing_new": False,
    }
    for key, value in defaults.items():
        if key not in st.session_state:
            st.session_state[key] = value


def signed_in() -> bool:
    """Report whether there is a user token to work with."""
    return st.session_state.auth is not None


def sign_in(
    *,
    email: str,
    username: str | None,
    access_token: str,
    expires_at: str,
    refresh_token: str,
) -> None:
    """Record a successful login or registration."""
    st.session_state.auth = {
        "email": email,
        "username": username,
        "access_token": access_token,
        "expires_at": expires_at,
        "refresh_token": refresh_token,
    }
    st.session_state.auth_error = None


def sign_out() -> None:
    """Drop every trace of the signed-in user from this browser session."""
    st.session_state.auth = None
    st.session_state.conversations = []
    st.session_state.active_session_id = None
    st.session_state.messages = []
    st.session_state.pending_query = None
    st.session_state.is_processing = False
    st.session_state.composing_new = False


def _expiry(auth: dict[str, Any]) -> datetime:
    """Parse the stored expiry, treating an unparseable one as already expired."""
    try:
        moment = datetime.fromisoformat(str(auth["expires_at"]))
    except ValueError:
        return datetime.now(UTC)
    return moment if moment.tzinfo else moment.replace(tzinfo=UTC)


def user_token(client: httpx.Client) -> str:
    """Return a user token that will still be valid for the next request."""
    auth = st.session_state.auth
    if auth is None:
        raise RuntimeError("no signed-in user")

    if _expiry(auth) - _REFRESH_MARGIN > datetime.now(UTC):
        return str(auth["access_token"])

    tokens = api_client.refresh_tokens(client, auth["refresh_token"])
    auth.update(
        access_token=tokens["access_token"],
        expires_at=tokens["expires_at"],
        # Single-use server-side: keeping the old value would fail the next
        # refresh and sign the user out mid-conversation.
        refresh_token=tokens["refresh_token"],
    )
    if tokens.get("email"):
        auth["email"] = tokens["email"]
    if "username" in tokens:
        auth["username"] = tokens.get("username")
    return str(tokens["access_token"])


# ----------------------------------------------------------------------
# Conversations
# ----------------------------------------------------------------------


def sync_conversations(client: httpx.Client) -> list[dict[str, Any]]:
    """Reload the sidebar from the database.

    Also the fix for an expired session token: ``GET /auth/sessions`` mints a
    fresh one per conversation, so re-listing is how the UI recovers rather than
    forcing a sign-in.
    """
    sessions = api_client.list_sessions(client, user_token(client))
    conversations = [
        {
            "session_id": item["session_id"],
            "name": item.get("name") or "",
            "token": item["token"]["access_token"],
        }
        for item in reversed(sessions)
    ]
    st.session_state.conversations = conversations

    known = {item["session_id"] for item in conversations}
    if st.session_state.active_session_id not in known:
        st.session_state.active_session_id = None
        st.session_state.messages = []
    return conversations


def active_conversation() -> dict[str, Any] | None:
    """Return the open conversation, or ``None`` when none is open."""
    session_id = st.session_state.active_session_id
    if session_id is None:
        return None
    return next(
        (
            item
            for item in st.session_state.conversations
            if item["session_id"] == session_id
        ),
        None,
    )


def open_conversation(session_id: str, messages: list[dict[str, Any]]) -> None:
    """Make a conversation the active one and show its history."""
    st.session_state.active_session_id = session_id
    st.session_state.messages = messages
    st.session_state.pending_query = None
    st.session_state.composing_new = False


def start_new_conversation() -> None:
    """Show an empty chat without creating anything server-side.

    The conversation row is created when the first message is sent, so
    clicking New chat repeatedly costs nothing and leaves nothing behind.
    """
    st.session_state.active_session_id = None
    st.session_state.messages = []
    st.session_state.pending_query = None
    st.session_state.composing_new = True


def add_conversation(session: dict[str, Any]) -> None:
    """Put a freshly created conversation at the top of the sidebar."""
    st.session_state.conversations.insert(
        0,
        {
            "session_id": session["session_id"],
            "name": session.get("name") or "",
            "token": session["token"]["access_token"],
        },
    )


def set_conversation_name(session_id: str, name: str) -> None:
    """Update a conversation's name in the sidebar without a full re-list."""
    for item in st.session_state.conversations:
        if item["session_id"] == session_id:
            item["name"] = name
            return


def remove_conversation(session_id: str) -> None:
    """Drop a deleted conversation from the sidebar and close it if it was open."""
    st.session_state.conversations = [
        item
        for item in st.session_state.conversations
        if item["session_id"] != session_id
    ]
    if st.session_state.active_session_id == session_id:
        st.session_state.active_session_id = None
        st.session_state.messages = []


__all__ = [
    "active_conversation",
    "add_conversation",
    "init",
    "open_conversation",
    "remove_conversation",
    "set_conversation_name",
    "sign_in",
    "sign_out",
    "signed_in",
    "start_new_conversation",
    "sync_conversations",
    "user_token",
]
