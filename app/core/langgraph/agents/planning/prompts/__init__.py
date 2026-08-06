"""Prompts owned by the planning agent, read once at import."""

from pathlib import Path

_PROMPTS_DIR = Path(__file__).parent

_CHOOSE_EXERCISES_TEMPLATE = (_PROMPTS_DIR / "choose_exercises.md").read_text(encoding="utf-8")

_NO_PREFERENCES = "The user has not stated any exercise preferences."


def load_choose_exercises_prompt(slots: str, preferences: str = "") -> str:
    """Render the exercise-selection prompt.

    Args:
        slots: Rendered slot list, each with its candidates.
        preferences: Free-text preferences extracted from the conversation.

    Returns:
        The formatted prompt.
    """
    return _CHOOSE_EXERCISES_TEMPLATE.format(
        slots=slots, preferences=preferences or _NO_PREFERENCES
    )


__all__ = ["load_choose_exercises_prompt"]
