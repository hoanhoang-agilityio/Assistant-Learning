"""User-facing wording, kept out of the components that render it.

The empty-state suggestions are not decoration: each one is written to land on a
different branch of the root graph — build, review,
change, revert, ask — so the first thing a new user clicks exercises a path the
assistant actually has. A suggestion for a branch that answers
"I'm not sure what you'd like me to do" is worse than no suggestion.
"""

from __future__ import annotations

_PASTED_PLAN_REVIEW = (
    "Can you review this plan for me?\n\n"
    "Day 1 — Upper: Bench Press 4x6-8, Barbell Row 4x8-10, "
    "Overhead Press 3x8-12, Lat Pulldown 3x8-12\n"
    "Day 2 — Lower: Back Squat 4x5-8, Romanian Deadlift 3x6-10, "
    "Leg Press 3x10-12, Standing Calf Raise 2x12-15\n"
    "Day 3 — Upper: Incline Dumbbell Press 4x8-10, Pull-Up 4x6-10, "
    "Seated Cable Row 3x8-12, Cable Lateral Raise 2x12-15"
)

# (icon, chip label, the message actually sent)
SUGGESTIONS: list[tuple[str, str, str]] = [
    (
        "🏋️",
        "Build me a plan",
        "I'd like a training plan. I'm 27, male, 171 cm, 73 kg, aiming for 70 kg. "
        "I can train 4 days a week at a gym and I'm moderately active.",
    ),
    (
        "📋",
        "Review a plan I have",
        _PASTED_PLAN_REVIEW,
    ),
    (
        "✏️",
        "Change my plan",
        "Can you change my plan to 3 days a week and drop the barbell work? "
        "I only have dumbbells for the next month.",
    ),
    (
        "🔬",
        "Ask a training question",
        "How much protein do I actually need to keep muscle while losing fat, "
        "and what does the evidence say about meal timing?",
    ),
]

WELCOME_TITLE = "👋 Hey! I'm PT AI — your personal training assistant."

WELCOME_BODY = (
    "Tell me your goal, your stats and how many days a week you can train, and I'll "
    "build the whole thing — workouts, calories and macros — then check it against "
    "the safety and volume rules before I hand it over. You can also paste a plan "
    "you already have, ask me to change the one you're on, or go back to an earlier "
    "version. Not sure where to start?"
)

NEW_CONVERSATION_NAME = "New chat"

# The confirm gate resumes on the user's next message, so the placeholder has to
# tell them a plain "yes" is what applies the change.
CHAT_PLACEHOLDER = "Ask, or tell me what to change… (reply “yes” to confirm a change)"

THINKING_LABEL = "Thinking…"

TAGLINE = "Your workout, nutrition & recovery coach"

# Failure wording. Each one says what did not happen, so the user knows whether
# to retry or to change something.
ERROR_COPY: dict[str, str] = {
    "chat_timeout": (
        "⏳ That turn is taking longer than usual. The work is still running on the "
        "server — reopen this conversation in a moment to see the answer."
    ),
    "chat_failed": "Couldn't get an answer",
    "history_failed": "Couldn't load that conversation",
    "new_chat_failed": "Couldn't start a new conversation",
    "rename_failed": "Couldn't rename this conversation",
    "delete_failed": "Couldn't delete this conversation",
    "clear_failed": "Couldn't clear this conversation",
    "sync_failed": "Couldn't refresh your conversations",
}


def conversation_title(name: str, fallback: str, *, max_length: int = 40) -> str:
    """Render a conversation's sidebar label.

    Args:
        name: The stored name, empty until the first turn names it.
        fallback: What to show while it is empty.
        max_length: Where to truncate.

    Returns:
        A single-line label.
    """
    title = " ".join((name or fallback).split())
    if len(title) <= max_length:
        return title
    return title[: max_length - 1].rstrip() + "…"


__all__ = [
    "CHAT_PLACEHOLDER",
    "ERROR_COPY",
    "NEW_CONVERSATION_NAME",
    "SUGGESTIONS",
    "TAGLINE",
    "THINKING_LABEL",
    "WELCOME_BODY",
    "WELCOME_TITLE",
    "conversation_title",
]
