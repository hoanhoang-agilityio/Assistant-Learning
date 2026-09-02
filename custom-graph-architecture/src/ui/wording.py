"""User-facing wording, kept out of the components that render it."""

from __future__ import annotations

# (icon, chip label, the message actually sent)
SUGGESTIONS: list[tuple[str, str, str]] = [
    (
        "🏋️",
        "Build me a plan",
        "I'd like a training plan. I'm 27, male, 178 cm, 80 kg, aiming for 75 kg. "
        "I train 4 days a week at a gym and I'm moderately active.",
    ),
    (
        "🌤️",
        "Ask something off-topic",
        "What's the weather like in Paris today?",
    ),
]


def welcome_title(username: str | None = None) -> str:
    """Build the empty-state greeting."""
    name = " ".join((username or "").split())
    if name:
        return f"👋 Hey {name}! I'm Coach AI — your training assistant."
    return "👋 Hey! I'm Coach AI — your training assistant."


WELCOME_BODY = (
    "Tell me your goal, your stats and how many days a week you can train, and I'll "
    "build a plan for you — then check it against a set of safety and volume rules "
    "before handing it over for your review. Not sure where to start?"
)

NEW_CONVERSATION_NAME = "New chat"

# hitl_review resumes on the user's next message, so the placeholder has to tell
# them a plain "yes" is what approves the plan.
CHAT_PLACEHOLDER = "Tell me about your goals… (reply “yes” to approve a plan)"

THINKING_LABEL = "Thinking…"

PROFILE_FORM_TITLE = "A few details before I plan"
PROFILE_FORM_SUBMIT = "Save and build my plan"
# What a form submission is called in the transcript. The graph resumes from the
# fields, not from this text, but the turn still has to read as something the user said.
PROFILE_FORM_SENT = "Here are my details."


def thought_for(seconds: float) -> str:
    """Label the settled step timeline with how long the turn took."""
    return f"Thought for {max(round(seconds), 1)}s"


TAGLINE = "Your training coach, built on a single LangGraph workflow"

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
    """Render a conversation's sidebar label."""
    title = " ".join((name or fallback).split())
    if len(title) <= max_length:
        return title
    return title[: max_length - 1].rstrip() + "…"


__all__ = [
    "CHAT_PLACEHOLDER",
    "ERROR_COPY",
    "NEW_CONVERSATION_NAME",
    "PROFILE_FORM_SENT",
    "PROFILE_FORM_SUBMIT",
    "PROFILE_FORM_TITLE",
    "SUGGESTIONS",
    "TAGLINE",
    "THINKING_LABEL",
    "WELCOME_BODY",
    "conversation_title",
    "thought_for",
    "welcome_title",
]
