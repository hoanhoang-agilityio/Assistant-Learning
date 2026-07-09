"""Streamlit UI for PT AI Core Deep Researcher."""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Any

_SRC_ROOT = Path(__file__).resolve().parent.parent
if str(_SRC_ROOT) not in sys.path:
    sys.path.insert(0, str(_SRC_ROOT))

import httpx
import streamlit as st

from ui.api_client import DEFAULT_REQUEST_TIMEOUT, get_api_base_url
from ui.components.chat import (
    handle_user_input,
    load_run_from_history,
    render_hitl_actions,
    render_messages,
    sync_active_run_if_needed,
)
from ui.components.sidebar import render_sidebar
from ui.components.welcome import render_welcome

st.set_page_config(page_title="PT AI", page_icon="PT", layout="wide")

_STYLES_PATH = Path(__file__).parent / "styles" / "style.css"


def inject_css() -> None:
    css = _STYLES_PATH.read_text(encoding="utf-8")
    st.markdown(f"<style>{css}</style>", unsafe_allow_html=True)


def _init_session_state() -> None:
    defaults: dict[str, Any] = {
        "run_id": None,
        "run_status": None,
        "api_base_url": get_api_base_url(),
        "messages": [],
        "run_history": [],
        "is_processing": False,
        "pending_query": None,
        "constraints_days": 4,
    }
    for key, value in defaults.items():
        if key not in st.session_state:
            st.session_state[key] = value


def _build_profile_from_form() -> dict[str, Any]:
    """Profile is extracted from the chat message by the planning subgraph."""
    return {}


def _restore_run_from_query_params() -> None:
    """Restore the active conversation from the URL after a page refresh.

    Only the single active run_id round-trips through the URL today, so this
    brings back the conversation you were last in — not the full sidebar
    history, and there's no way to switch to a different stored conversation
    from a fresh browser session yet.
    """
    if st.session_state.run_id is not None:
        return
    query_run_id = st.query_params.get("run_id")
    if not query_run_id:
        return
    with httpx.Client(
        base_url=st.session_state.api_base_url,
        timeout=DEFAULT_REQUEST_TIMEOUT,
    ) as client:
        try:
            load_run_from_history(client, query_run_id)
        except httpx.HTTPError:
            # Backend no longer knows this run (e.g. it restarted) - drop the stale link.
            st.query_params.pop("run_id", None)


def main() -> None:
    _init_session_state()
    _restore_run_from_query_params()
    inject_css()
    render_sidebar()

    messages: list[dict[str, str]] = st.session_state.messages
    is_processing: bool = st.session_state.is_processing

    if not messages and not is_processing:
        render_welcome()

    render_messages(messages)

    with httpx.Client(
        base_url=st.session_state.api_base_url,
        timeout=DEFAULT_REQUEST_TIMEOUT,
    ) as client:
        if sync_active_run_if_needed(client):
            st.rerun()

        status = st.session_state.run_status
        run_id = st.session_state.run_id
        waiting_for_approval = (
            run_id
            and status
            and status.get("status") == "waiting_hitl"
            and status.get("hitl_type", "approval") == "approval"
            and status.get("approval_status") not in {"rejected", "approved"}
        )
        if waiting_for_approval:
            render_hitl_actions(client, run_id, status)

    chat_placeholder = (
        "Want any changes? (e.g. train 5 days per week)…"
        if waiting_for_approval
        else "Tell me your goal, body stats, and training preferences…"
    )
    query = st.chat_input(
        chat_placeholder,
        disabled=is_processing,
    )
    pending_query = st.session_state.pending_query
    active_query = query or pending_query

    if active_query and not is_processing:
        st.session_state.pending_query = None
        with httpx.Client(
            base_url=st.session_state.api_base_url,
            timeout=DEFAULT_REQUEST_TIMEOUT,
        ) as client:
            handle_user_input(
                client,
                active_query,
                build_profile=_build_profile_from_form,
            )
        st.rerun()


if __name__ == "__main__":
    main()
