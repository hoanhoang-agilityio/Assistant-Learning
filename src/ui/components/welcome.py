"""Empty-state suggestions for new chats."""

import streamlit as st

SUGGESTIONS = [
    (
        "🔥",
        "4-day fat loss plan",
        "I want a 4-day training plan to lose weight with strength training. "
        "27, male, 171 cm, 73 kg, goal 70 kg.",
    ),
    (
        "🧮",
        "Daily calories",
        "Help me calculate my daily calorie and protein needs for fat loss.",
    ),
    (
        "🥗",
        "High-protein meals",
        "Suggest high-protein meals that support muscle recovery.",
    ),
    (
        "🏃",
        "Endurance block",
        "I want to improve cardiovascular endurance over 8 weeks.",
    ),
]


def render_welcome() -> None:
    st.markdown(
        '<div class="pt-welcome">'
        '<p class="pt-welcome__title">👋 Hey! I\'m PT AI — your personal training assistant.</p>'
        '<p class="pt-empty-state">Tell me your goal, stats, and how many days a week you can train. '
        "I'll put together a full plan — workouts, nutrition, recovery — and check in with you "
        "before anything is final. Not sure where to start? Try one of these:</p>"
        "</div>",
        unsafe_allow_html=True,
    )
    cols = st.columns(2)
    for index, (icon, label, query) in enumerate(SUGGESTIONS):
        col = cols[index % 2]
        if col.button(f"{icon}  {label}", key=f"suggestion_{index}", use_container_width=True):
            st.session_state.pending_query = query
            st.rerun()
