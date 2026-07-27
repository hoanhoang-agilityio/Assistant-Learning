"""Structured profile form for the User subgraph's HITL 'profile_form' pause.

Renders the minimal set of biometric fields the orchestrator needs, pre-filled from
whatever the LLM already extracted from chat, and blocks submission client-side until the
required fields are present and within the same bounds core/profile/schema.py enforces
server-side -- so the user fixes problems here instead of round-tripping through a rejected
resume.
"""

from __future__ import annotations

from typing import Any

import httpx
import streamlit as st
import streamlit.components.v1 as components

from ui.api_client import resume_run
from ui.components.chat import (
    TimelineTracker,
    assistant_message_from_status,
    attach_timeline,
    build_timeline_message,
    run_guarded_backend_action,
    update_run_history_status,
)
from ui.copy import HITL_TYPE_COPY, feasibility_messages

SEX_OPTIONS: tuple[str, ...] = ("male", "female")

_REQUIRED_FIELD_ERROR = "This field is required."

# Field name -> widget key prefix (combined with "_{run_id}" to form the actual st widget
# key). Kept in sync with the keys used below so _focus_field can target the right
# widget via Streamlit's automatic ".st-key-<key>" container class.
_FIELD_KEY_PREFIXES: dict[str, str] = {
    "age": "pf_age",
    "sex": "pf_sex",
    "height_cm": "pf_height_cm",
    "current_weight_kg": "pf_current_weight_kg",
    "target_weight_kg": "pf_target_weight_kg",
}


def _as_int(value: Any) -> int | None:
    if value is None:
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _as_float(value: Any) -> float | None:
    if value is None:
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _option_index(options: tuple[str, ...], value: Any) -> int | None:
    if value in options:
        return options.index(value)
    return None


def _validate(values: dict[str, Any]) -> dict[str, str]:
    errors: dict[str, str] = {}

    if values["age"] is None:
        errors["age"] = _REQUIRED_FIELD_ERROR
    elif not (13 <= values["age"] <= 100):
        errors["age"] = "Age must be between 13 and 100."

    if not values["sex"]:
        errors["sex"] = _REQUIRED_FIELD_ERROR

    if values["height_cm"] is None:
        errors["height_cm"] = _REQUIRED_FIELD_ERROR
    elif not (0 < values["height_cm"] <= 250):
        errors["height_cm"] = "Height must be between 1 and 250 cm."

    if values["current_weight_kg"] is None:
        errors["current_weight_kg"] = _REQUIRED_FIELD_ERROR
    elif not (0 < values["current_weight_kg"] <= 300):
        errors["current_weight_kg"] = "Weight must be between 1 and 300 kg."

    if values["target_weight_kg"] is None:
        errors["target_weight_kg"] = _REQUIRED_FIELD_ERROR
    elif not (0 < values["target_weight_kg"] <= 300):
        errors["target_weight_kg"] = "Target weight must be between 1 and 300 kg."

    return errors


def _focus_field(run_id: str, field: str) -> None:
    """Scroll to and focus the first invalid field's widget after a failed submit.

    Streamlit's iframe shares the same origin as the parent page, so reaching through
    ``window.parent.document`` to drive focus on a plain HTML input/select is a common
    (if hacky) escape hatch — there's no first-class Streamlit API for this.
    """
    prefix = _FIELD_KEY_PREFIXES.get(field)
    if not prefix:
        return
    selector = f".st-key-{prefix}_{run_id} input, .st-key-{prefix}_{run_id} [data-baseweb='select']"
    components.html(
        f"""<script>
        setTimeout(function() {{
            var el = window.parent.document.querySelector("{selector}");
            if (el) {{
                el.scrollIntoView({{behavior: "smooth", block: "center"}});
                el.focus();
            }}
        }}, 50);
        </script>""",
        height=0,
    )


def render_profile_form(client: httpx.Client, run_id: str, status: dict[str, Any]) -> None:
    """Render the structured profile-form HITL step and handle its submission."""
    payload = status.get("profile_form") or {}
    profile = payload.get("profile") or {}
    issues = feasibility_messages(payload.get("feasibility_issues") or [])

    st.markdown(
        f'<div class="pt-hitl-banner">🙋 <span>{HITL_TYPE_COPY["profile_form"]}</span></div>',
        unsafe_allow_html=True,
    )
    if issues:
        st.markdown(
            '<div class="pt-feasibility-banner">'
            + "".join(f"<p>⚠️ {message}</p>" for message in issues)
            + "</div>",
            unsafe_allow_html=True,
        )

    with st.form(f"profile_form_{run_id}", border=True):
        st.markdown(
            '<p class="pt-profile-form__title">Tell us about yourself</p>'
            '<p class="pt-profile-form__subtitle">'
            "We'll use this information to personalize your fitness plan.</p>",
            unsafe_allow_html=True,
        )

        col1, col2 = st.columns(2)
        with col1:
            age = st.number_input(
                "Age",
                min_value=13,
                max_value=100,
                value=_as_int(profile.get("age")),
                step=1,
                key=f"pf_age_{run_id}",
            )
        with col2:
            sex = st.selectbox(
                "Sex",
                options=SEX_OPTIONS,
                index=_option_index(SEX_OPTIONS, profile.get("sex")),
                format_func=str.capitalize,
                placeholder="Select…",
                key=f"pf_sex_{run_id}",
            )

        col3, col4 = st.columns(2)
        with col3:
            height_cm = st.number_input(
                "Height (cm)",
                min_value=1.0,
                max_value=250.0,
                value=_as_float(profile.get("height_cm")),
                step=1.0,
                key=f"pf_height_cm_{run_id}",
            )
        with col4:
            current_weight_kg = st.number_input(
                "Current weight (kg)",
                min_value=1.0,
                max_value=300.0,
                value=_as_float(profile.get("current_weight_kg")),
                step=0.5,
                key=f"pf_current_weight_kg_{run_id}",
            )

        target_weight_kg = st.number_input(
            "Target weight (kg)",
            min_value=1.0,
            max_value=300.0,
            value=_as_float(profile.get("target_weight_kg")),
            step=0.5,
            key=f"pf_target_weight_kg_{run_id}",
        )

        submitted = st.form_submit_button("Continue →", type="primary")

    if not submitted:
        return

    values = {
        "age": age,
        "sex": sex,
        "height_cm": height_cm,
        "current_weight_kg": current_weight_kg,
        "target_weight_kg": target_weight_kg,
    }
    errors = _validate(values)
    if errors:
        st.markdown(
            '<div class="pt-form-error">⚠ Please complete all required fields.</div>',
            unsafe_allow_html=True,
        )
        _focus_field(run_id, next(iter(errors)))
        return

    form_data = {key: value for key, value in values.items() if value is not None}

    st.session_state.messages.append({"role": "user", "content": "Submitted my profile details."})

    def do_submit() -> dict[str, Any]:
        row = st.empty()
        tracker = TimelineTracker(row)
        updated = resume_run(
            client,
            run_id,
            form_data=form_data,
            on_progress=tracker.on_progress,
        )
        return attach_timeline(updated, tracker)

    def on_success(updated: dict[str, Any]) -> None:
        st.session_state.run_status = updated
        st.session_state.messages.append(
            build_timeline_message(updated, assistant_message_from_status(updated))
        )
        update_run_history_status(run_id, updated.get("status", "unknown"))

    run_guarded_backend_action(
        do_submit,
        on_success=on_success,
        timeout_message=(
            "⏳ Still saving your details — this is taking a little longer than "
            "usual. Please wait a moment…"
        ),
        error_prefix="Couldn't save your profile details",
        rerun_on_settle=True,
    )
