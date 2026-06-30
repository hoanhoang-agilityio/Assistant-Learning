"""Sidebar: brand, history, profile summary, and settings."""

from __future__ import annotations

from typing import Any

import httpx
import streamlit as st

from core.profile.labels import format_activity_label, format_goal_label
from ui.api_client import DEFAULT_REQUEST_TIMEOUT, get_run
from ui.components.chat import _rebuild_messages_from_run, load_run_from_history


def _has_profile_data() -> bool:
    return st.session_state.get("profile_age") is not None


def _render_profile_summary() -> None:
    if not _has_profile_data():
        return
    age = st.session_state.get("profile_age", "-")
    goal = format_goal_label(str(st.session_state.get("profile_goal", "-")))
    weight = st.session_state.get("profile_current_weight_kg", "-")
    st.markdown(
        f"""
        <div class="profile-card">
            <strong>Profile</strong><br>
            Age: {age} · Goal: {goal}<br>
            Weight: {weight} kg
        </div>
        """,
        unsafe_allow_html=True,
    )


def _render_profile_settings() -> None:
    col_a, col_b = st.columns(2)
    st.session_state.profile_age = col_a.number_input(
        "Age",
        min_value=16,
        max_value=90,
        value=st.session_state.get("profile_age", 30),
        key="profile_age_input",
    )
    st.session_state.profile_sex = col_b.selectbox(
        "Sex",
        options=["male", "female"],
        index=0 if st.session_state.get("profile_sex", "male") == "male" else 1,
        key="profile_sex_input",
    )
    st.session_state.profile_height_cm = col_a.number_input(
        "Height (cm)",
        min_value=120,
        max_value=220,
        value=st.session_state.get("profile_height_cm", 175),
        key="profile_height_input",
    )
    st.session_state.profile_current_weight_kg = col_b.number_input(
        "Current weight (kg)",
        min_value=40.0,
        max_value=200.0,
        value=float(st.session_state.get("profile_current_weight_kg", 85.0)),
        key="profile_current_weight_input",
    )
    st.session_state.profile_target_weight_kg = col_a.number_input(
        "Target weight (kg)",
        min_value=40.0,
        max_value=200.0,
        value=float(st.session_state.get("profile_target_weight_kg", 75.0)),
        key="profile_target_weight_input",
    )
    st.session_state.profile_activity_level = col_b.selectbox(
        "Activity level",
        options=[
            "sedentary",
            "gym_1x_week",
            "gym_3x_week",
            "gym_4x_week",
            "gym_5x_week",
            "gym_6x_week",
        ],
        format_func=format_activity_label,
        index=[
            "sedentary",
            "gym_1x_week",
            "gym_3x_week",
            "gym_4x_week",
            "gym_5x_week",
            "gym_6x_week",
        ].index(st.session_state.get("profile_activity_level", "gym_3x_week")),
        key="profile_activity_input",
    )
    goal_options = ["fat_loss", "muscle_gain", "strength", "endurance", "general_fitness"]
    current_goal = st.session_state.get("profile_goal", "fat_loss")
    st.session_state.profile_goal = st.selectbox(
        "Goal",
        options=goal_options,
        format_func=format_goal_label,
        index=goal_options.index(current_goal) if current_goal in goal_options else 0,
        key="profile_goal_input",
    )


def _truncate_query(query: str, max_length: int = 40) -> str:
    if len(query) <= max_length:
        return query
    return query[: max_length - 3] + "..."


def render_sidebar() -> None:
    with st.sidebar:
        st.markdown('<div class="sidebar-brand">🏋️ PT AI</div>', unsafe_allow_html=True)

        if st.button("New Chat", type="primary", use_container_width=True, key="new_chat"):
            st.session_state.run_id = None
            st.session_state.run_status = None
            st.session_state.messages = []
            st.session_state.pending_query = None
            st.rerun()

        st.divider()

        history: list[dict[str, Any]] = st.session_state.run_history
        if history:
            st.markdown(
                '<div class="pt-sidebar__section"><p class="pt-sidebar__label">History</p></div>',
                unsafe_allow_html=True,
            )
            active_run_id = st.session_state.run_id
            for index, item in enumerate(reversed(history)):
                run_id = item["run_id"]
                title = _truncate_query(item.get("query", run_id))
                run_status = item.get("status", "unknown")
                label = f"{title} ({run_status})"
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

        _render_profile_summary()

        with st.expander("Settings", expanded=False):
            st.session_state.api_base_url = st.text_input(
                "API base URL",
                value=st.session_state.api_base_url,
                key="api_base_url_input",
            )
            st.session_state.use_settings_profile = st.checkbox(
                "Use profile from settings below",
                value=st.session_state.get("use_settings_profile", False),
                help=(
                    "When off, profile fields are parsed from your chat message. "
                    "When on, the values below override what you type in chat."
                ),
                key="use_settings_profile_input",
            )
            _render_profile_settings()
            st.session_state.constraints_days = st.slider(
                "Training days per week",
                min_value=2,
                max_value=6,
                value=st.session_state.get("constraints_days", 4),
                key="constraints_days_slider",
            )
            if st.button("Refresh status", key="refresh_status") and st.session_state.run_id:
                with httpx.Client(
                    base_url=st.session_state.api_base_url,
                    timeout=DEFAULT_REQUEST_TIMEOUT,
                ) as client:
                    status = get_run(client, st.session_state.run_id)
                    st.session_state.run_status = status
                    st.session_state.messages = _rebuild_messages_from_run(status)
                st.rerun()
