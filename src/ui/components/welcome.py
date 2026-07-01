"""Empty-state suggestions for new chats."""

import streamlit as st

SUGGESTIONS = [
    (
        "4-day fat loss plan",
        "I want a 4-day training plan to lose weight with strength training. "
        "27, male, 171 cm, 73 kg, goal 70 kg.",
    ),
    (
        "Daily calories",
        "Help me calculate my daily calorie and protein needs for fat loss.",
    ),
    (
        "High-protein meals",
        "Suggest high-protein meals that support muscle recovery.",
    ),
    (
        "Endurance block",
        "I want to improve cardiovascular endurance over 8 weeks.",
    ),
]


def render_welcome() -> None:
    st.markdown(
        '<p class="pt-empty-state">Describe your goal, stats, and constraints in one message. '
        "PT AI will build a plan and ask for approval when ready.</p>",
        unsafe_allow_html=True,
    )
    cols = st.columns(2)
    for index, (label, query) in enumerate(SUGGESTIONS):
        col = cols[index % 2]
        if col.button(label, key=f"suggestion_{index}", use_container_width=True):
            st.session_state.pending_query = query
            st.rerun()
