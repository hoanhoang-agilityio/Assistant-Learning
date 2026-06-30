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
from ui.components.chat import handle_user_input, render_hitl_form, render_messages
from ui.components.header import render_header
from ui.components.sidebar import render_sidebar
from ui.components.welcome import render_welcome

st.set_page_config(page_title="PT AI", page_icon="🏋️", layout="wide")

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
        "profile_age": 30,
        "profile_sex": "male",
        "profile_height_cm": 175,
        "profile_current_weight_kg": 85.0,
        "profile_target_weight_kg": 75.0,
        "profile_activity_level": "gym_3x_week",
        "profile_goal": "fat_loss",
        "use_settings_profile": False,
    }
    for key, value in defaults.items():
        if key not in st.session_state:
            st.session_state[key] = value


def _build_profile_from_form() -> dict[str, Any]:
    if not st.session_state.get("use_settings_profile", False):
        return {}
    return {
        "age": st.session_state.get("profile_age"),
        "sex": st.session_state.get("profile_sex"),
        "height_cm": st.session_state.get("profile_height_cm"),
        "current_weight_kg": st.session_state.get("profile_current_weight_kg"),
        "target_weight_kg": st.session_state.get("profile_target_weight_kg"),
        "activity_level": st.session_state.get("profile_activity_level"),
        "goal": st.session_state.get("profile_goal"),
    }


def main() -> None:
    _init_session_state()
    inject_css()
    render_sidebar()
    render_header()

    messages: list[dict[str, str]] = st.session_state.messages
    is_processing: bool = st.session_state.is_processing

    if not messages and not is_processing:
        render_welcome()

    render_messages(messages)

    status = st.session_state.run_status
    run_id = st.session_state.run_id
    if run_id and status:
        with httpx.Client(
            base_url=st.session_state.api_base_url,
            timeout=DEFAULT_REQUEST_TIMEOUT,
        ) as client:
            if status.get("status") == "waiting_hitl":
                hitl_type = status.get("hitl_type") or "approval"
                if hitl_type != "clarification":
                    render_hitl_form(client, run_id, status)

    query = st.chat_input("Ask about workouts, nutrition, or recovery…")
    pending_query = st.session_state.pending_query
    active_query = query or pending_query

    if active_query:
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
