"""Prompts owned by the supervisor, read once at import."""

from datetime import UTC, datetime
from pathlib import Path

from app.core.configs.config import settings
from app.services.profile import FIELD_LABELS, GOAL_LABELS

_PROMPTS_DIR = Path(__file__).parent

_SUPERVISOR_PROMPT_TEMPLATE = (_PROMPTS_DIR / "supervisor.md").read_text(encoding="utf-8")

_NO_MEMORY_BODY = "Nothing recorded yet."
# Deliberately says "none available" rather than "this user has none": a
# caller may withhold episodic context on purpose, and a model told the user
# has no history will eventually say so to their face.
_NO_EPISODES_BODY = "None available for this turn."


def load_supervisor_prompt(
    semantic_context: str = "",
    plan_context: str = "",
    episodic_context: str = "",
    missing_fields: list[str] | None = None,
    goal_conflict: dict[str, str] | None = None,
    intent_hint: str | None = None,
) -> str:
    """Render the supervisor's system prompt.

    Three blocks are conditional, and each of them replaces a node the old root
    graph had. ``missing_block`` is ``ask_missing``; ``conflict_block`` is
    ``ask_goal``; ``hint_block`` is what ``classify`` used to route with. They
    are rendered as facts and questions rather than as instructions to call a
    particular tool, because the supervisor may legitimately disagree with the
    hint after reading a tool result — that recovery is one of the reasons the
    router was replaced.

    Args:
        semantic_context: Standing facts about the user, rendered from their
            profile *after* this turn's facts were merged.
        plan_context: The plan they hold and its targets, as read-only text.
        episodic_context: Summaries of earlier sessions, newest first.
        missing_fields: Profile fields a tool refused for want of. Named here so
            the question covers all of them in one message.
        goal_conflict: A goal this turn implies against the stored one.
        intent_hint: The topic gate's classification. Advisory.

    Returns:
        The formatted supervisor prompt.
    """
    return _SUPERVISOR_PROMPT_TEMPLATE.format(
        agent_name=f"{settings.PROJECT_NAME} Agent",
        current_date_and_time=datetime.now(UTC).strftime("%Y-%m-%d %H:%M:%S UTC"),
        plan_context=plan_context or "They have no saved plan.",
        semantic_context=semantic_context or _NO_MEMORY_BODY,
        episodic_context=episodic_context or _NO_EPISODES_BODY,
        missing_block=_missing_block(missing_fields or []),
        conflict_block=_conflict_block(goal_conflict),
        hint_block=_hint_block(intent_hint),
    )


def _missing_block(fields: list[str]) -> str:
    """Render the outstanding profile fields as one question to ask.

    All of them at once, deliberately. Trickling them out one per turn is how a
    user ends up filling in a form, and a fixed wording means someone who answers
    half of them sees the same question again for the rest.

    Args:
        fields: Field names a tool refused for want of.

    Returns:
        The block, or an empty string when nothing is outstanding.
    """
    if not fields:
        return ""

    labels = "\n".join(f"- {FIELD_LABELS.get(field, field)}" for field in fields)
    return (
        "# Ask for these before doing anything else\n\n"
        "A tool refused because these are unanswered. Ask for all of them in one "
        "message, and do not guess any of them:\n\n" + labels
    )


def _conflict_block(conflict: dict[str, str] | None) -> str:
    """Render the goal question, when this turn contradicts the stored goal.

    The turn stops on it rather than picking one. Going on with either goal is
    the guess this block exists to avoid: it flips the calorie target from a
    deficit to a surplus, and the answer would look authoritative either way.

    Args:
        conflict: The stored and implied goals.

    Returns:
        The block, or an empty string when there is no conflict.
    """
    if not conflict:
        return ""

    stored = GOAL_LABELS.get(conflict["stored"], conflict["stored"])
    implied = GOAL_LABELS.get(conflict["implied"], conflict["implied"])
    return (
        "# Their goal is in question\n\n"
        f"Their profile says **{stored}**, but this message reads more like **{implied}**. "
        "That moves the calorie target in opposite directions, so ask which one to plan "
        "for — put the two side by side and let them choose. Do not build or change a plan "
        "until they answer."
    )


def _hint_block(intent: str | None) -> str:
    """Render the topic gate's classification as advice, not as an instruction.

    Args:
        intent: What the classifier thought this turn was.

    Returns:
        The block, or an empty string when there is no hint.
    """
    if not intent:
        return ""

    return (
        f"# A hint\n\nA classifier read this turn as `{intent}`. It saw the conversation and "
        "nothing else, so treat it as a starting point rather than an instruction — if a tool "
        "result tells you otherwise, believe the tool result."
    )


__all__ = ["load_supervisor_prompt"]
