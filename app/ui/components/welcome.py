"""The empty state: what the assistant can do, as four things you can click."""

from __future__ import annotations

import streamlit as st

from app.ui.wording import SUGGESTIONS, WELCOME_BODY, WELCOME_TITLE


def render_welcome() -> None:
    """Draw the greeting and the suggestion chips.

    A clicked chip becomes ``pending_query`` and the script reruns, so the
    message travels the same path as anything typed into the chat box — one
    send path, not two.
    """
    st.markdown(
        '<div class="pt-welcome">'
        f'<p class="pt-welcome__title">{WELCOME_TITLE}</p>'
        f'<p class="pt-empty-state">{WELCOME_BODY}</p>'
        "</div>",
        unsafe_allow_html=True,
    )

    columns = st.columns(2)
    for index, (icon, label, query) in enumerate(SUGGESTIONS):
        column = columns[index % 2]
        if column.button(f"{icon}  {label}", key=f"suggestion_{index}", use_container_width=True):
            st.session_state.pending_query = query
            st.rerun()


__all__ = ["render_welcome"]
