"""Empty-state suggestions for new chats."""

import streamlit as st

_WEIGHT_GAIN_PLAN_REVIEW = (
    "Help me check whether this fitness plan is suitable for weight gain. "
    "Fitness Plan Draft Program Blueprint Archetype: fat_loss_moderate "
    "Phases: Weeks 1-4: metabolic (volume x1.0) Weeks 5-8: metabolic (volume x0.95) "
    "Increase load or reps when all sets reach the top of the prescribed rep range. "
    "Use a deload if performance or recovery drops for two consecutive weeks. "
    "Macro Targets Calories: 2087 kcal Protein: 131 g Carbs: 260 g Fat: 58 g "
    "Training Plan Split: Upper/Lower (4-day) (Fat loss with lean-mass retention)\n\n"
    "Day 1 — Day 1 Focus: Upper Push/Pull\n\n"
    "Barbell Bench Press: 4 x 6-8 Chest-Supported Row: 4 x 8-10 "
    "Incline Dumbbell Press: 3 x 8-12 Lat Pulldown: 3 x 8-12 "
    "Cable Lateral Raise: 2 x 12-15 Day 2 — Day 2 Focus: Lower Squat Emphasis\n\n"
    "Back Squat: 4 x 5-8 Romanian Deadlift: 3 x 6-10 Leg Press: 3 x 10-12 "
    "Leg Curl: 3 x 10-15 Standing Calf Raise: 2 x 12-15 "
    "Day 3 — Day 3 Focus: Upper Vertical Push/Pull\n\n"
    "Overhead Press: 4 x 6-8 Pull-Up: 4 x 6-10 Dumbbell Bench Press: 3 x 8-12 "
    "Seated Cable Row: 3 x 8-12 Face Pull: 2 x 12-15 "
    "Day 4 — Day 4 Focus: Lower Hinge Emphasis\n\n"
    "Deadlift: 3 x 3-5 Front Squat: 3 x 6-8 Bulgarian Split Squat: 3 x 8-10 "
    "Hip Thrust: 3 x 8-12 Hanging Knee Raise: 2 x 10-15"
)

SUGGESTIONS = [
    (
        "🔥",
        "4-day fat loss plan",
        "I want a 4-day training plan to lose weight with strength training. "
        "27, male, 171 cm, 73 kg, goal 70 kg.",
    ),
    (
        "🧮",
        "Weight loss macro check",
        "I want to know if my current macros are appropriate for weight loss. "
        "I'm currently consuming 3,000 calories per day.",
    ),
    (
        "📋",
        "Weight gain plan check",
        _WEIGHT_GAIN_PLAN_REVIEW,
    ),
    (
        "🔬",
        "Endurance training research",
        "What does current research say about the most effective training approach "
        "for improving cardiovascular endurance over 8 weeks — zone 2, HIIT, or "
        "polarized periodization? Please cite recent evidence and guidelines.",
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
