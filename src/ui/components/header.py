"""Page header component."""

import streamlit as st


def render_header() -> None:
    st.markdown(
        """
        <div class="pt-header">
            <h1 class="pt-header__title">🏋️ Personal Trainer AI</h1>
            <p class="pt-header__subtitle">Workout • Nutrition • Recovery</p>
            <hr class="pt-header__divider" />
        </div>
        """,
        unsafe_allow_html=True,
    )
