"""Welcome screen with suggestion chips."""

import streamlit as st

SUGGESTIONS = [
    (
        "Create a workout plan",
        "I want a 4-day training plan to lose weight with strength training.",
    ),
    ("Calculate calories", "Help me calculate my daily calorie needs for fat loss."),
    ("Suggest meals", "Suggest high-protein meals that support muscle recovery."),
    ("Improve endurance", "I want to improve my cardiovascular endurance over 8 weeks."),
]


def render_welcome() -> None:
    st.markdown(
        """
        <div class="welcome-panel">
            <h2>Welcome to PT AI</h2>
            <p>Your personal trainer for workouts, nutrition, and recovery.</p>
        </div>
        """,
        unsafe_allow_html=True,
    )
    st.markdown('<p class="pt-suggestions-label">Try asking</p>', unsafe_allow_html=True)
    cols = st.columns(2)
    for index, (label, query) in enumerate(SUGGESTIONS):
        col = cols[index % 2]
        if col.button(label, key=f"suggestion_{index}", use_container_width=True):
            st.session_state.pending_query = query
            st.rerun()
