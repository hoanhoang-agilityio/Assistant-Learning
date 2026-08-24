"""The empty state: what the coach can do, as clickable suggestions."""

from __future__ import annotations

from html import escape

import streamlit as st

from src.ui.wording import SUGGESTIONS, WELCOME_BODY, welcome_title


def render_welcome() -> None:
    """Draw the greeting and the suggestion chips.

    A clicked chip becomes ``pending_query`` and the script reruns, so the
    message travels the same path as anything typed into the chat box — one
    send path, not two.
    """
    auth = st.session_state.get("auth") or {}
    title = welcome_title(auth.get("username"))
    st.markdown(
        '<div class="pt-welcome">'
        f'<p class="pt-welcome__title">{escape(title)}</p>'
        f'<p class="pt-empty-state">{escape(WELCOME_BODY)}</p>'
        "</div>",
        unsafe_allow_html=True,
    )

    columns = st.columns(2)
    for index, (icon, label, query) in enumerate(SUGGESTIONS):
        column = columns[index % 2]
        if column.button(
            f"{icon}  {label}", key=f"suggestion_{index}", use_container_width=True
        ):
            st.session_state.pending_query = query
            st.rerun()


__all__ = ["render_welcome"]
