"""Sidebar: brand, new chat, and run history."""

from __future__ import annotations

from typing import Any

import httpx
import streamlit as st

from ui.api_client import DEFAULT_REQUEST_TIMEOUT
from ui.components.chat import load_run_from_history


def _truncate_query(query: str, max_length: int = 40) -> str:
    if len(query) <= max_length:
        return query
    return query[: max_length - 3] + "..."


def _status_label(status: str) -> str:
    labels = {
        "running": "running",
        "waiting_hitl": "needs input",
        "completed": "done",
        "failed": "failed",
    }
    return labels.get(status, status)


def render_sidebar() -> None:
    with st.sidebar:
        st.markdown('<div class="sidebar-brand">PT AI</div>', unsafe_allow_html=True)
        st.markdown(
            '<p class="pt-sidebar__tagline">Workout, nutrition, recovery</p>',
            unsafe_allow_html=True,
        )

        if st.button("New chat", type="primary", use_container_width=True, key="new_chat"):
            st.session_state.run_id = None
            st.session_state.run_status = None
            st.session_state.messages = []
            st.session_state.pending_query = None
            st.rerun()

        history: list[dict[str, Any]] = st.session_state.run_history
        if history:
            st.markdown(
                '<div class="pt-sidebar__section"><p class="pt-sidebar__label">Recent</p></div>',
                unsafe_allow_html=True,
            )
            active_run_id = st.session_state.run_id
            for index, item in enumerate(reversed(history)):
                run_id = item["run_id"]
                title = _truncate_query(item.get("query", run_id))
                run_status = _status_label(item.get("status", "unknown"))
                label = f"{title} · {run_status}"
                if run_id == active_run_id:
                    label = f"● {label}"
                if st.button(
                    label,
                    key=f"history_{run_id}_{index}",
                    use_container_width=True,
                ):
                    with httpx.Client(
                        base_url=st.session_state.api_base_url,
                        timeout=DEFAULT_REQUEST_TIMEOUT,
                    ) as client:
                        load_run_from_history(client, run_id)
                    st.rerun()
