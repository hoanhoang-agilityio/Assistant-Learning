"""The profile form: the fields the graph is waiting on, rendered as one form.

The field list is not written here. It arrives on the ``form`` frame, derived by the
backend from the profile model itself, so a field added or a bound changed there shows
up here without this file being touched.
"""

from __future__ import annotations

from typing import Any

import streamlit as st

from src.ui.wording import PROFILE_FORM_SUBMIT, PROFILE_FORM_TITLE

CHOICE = "choice"
INTEGER = "integer"
NUMBER = "number"

_UNSET = "—"


def pending_form() -> dict[str, Any] | None:
    """The form the graph is waiting on, or None when it is waiting on nothing."""
    return st.session_state.get("pending_form")


def _choice(field: dict[str, Any], current: Any) -> Any:
    """One fixed-choice field, starting unset rather than on an arbitrary first option."""
    options = [_UNSET, *field["options"]]
    index = options.index(current) if current in options else 0
    chosen = st.selectbox(
        field["label"],
        options,
        index=index,
        help=field["description"] or None,
        key=f"profile_form_{field['name']}",
    )
    return None if chosen == _UNSET else chosen


def _number(field: dict[str, Any], current: Any) -> Any:
    """One numeric field, bounded by whatever the model declares."""
    integer = field["kind"] == INTEGER
    minimum = field["minimum"]
    maximum = field["maximum"]
    step = 1 if integer else 0.5

    value = st.number_input(
        field["label"],
        value=(int(current) if integer else float(current))
        if current is not None
        else None,
        min_value=(int(minimum) if integer else float(minimum))
        if minimum is not None
        else None,
        max_value=(int(maximum) if integer else float(maximum))
        if maximum is not None
        else None,
        step=step,
        help=field["description"] or None,
        placeholder="",
        key=f"profile_form_{field['name']}",
    )
    return value


def _input(field: dict[str, Any], values: dict[str, Any]) -> Any:
    """One field of the form, rendered for the kind of value it holds."""
    current = values.get(field["name"])
    if field["kind"] == CHOICE:
        return _choice(field, current)
    return _number(field, current)


def render_profile_form(form: dict[str, Any]) -> dict[str, Any] | None:
    """Draw the form and return what was filled in, or None until it is submitted."""
    errors: dict[str, str] = form.get("errors") or {}
    values: dict[str, Any] = form.get("values") or {}

    with st.form("profile_form", clear_on_submit=False):
        st.markdown(f"#### {PROFILE_FORM_TITLE}")
        submitted: dict[str, Any] = {}
        for field in form.get("fields", []):
            submitted[field["name"]] = _input(field, values)
            message = errors.get(field["name"])
            if message:
                st.caption(f":red[{message}]")

        if not st.form_submit_button(PROFILE_FORM_SUBMIT, type="primary"):
            return None

    return {name: value for name, value in submitted.items() if value is not None}


__all__ = ["pending_form", "render_profile_form"]
