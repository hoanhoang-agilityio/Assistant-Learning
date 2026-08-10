"""Prompt templates, read from disk once at import.

Every prompt is a ``.md`` file next to this module so it is reviewable in a diff.
The files are read at import time and only formatted per call — a node that
opens a file on every request pays disk I/O inside the event loop.

Templates use ``str.format``, so any literal brace in a prompt body must be
doubled (``{{`` / ``}}``).
"""

from datetime import UTC, datetime
from pathlib import Path

from app.core.configs.config import settings

_PROMPTS_DIR = Path(__file__).parent

_SYSTEM_PROMPT_TEMPLATE = (_PROMPTS_DIR / "system.md").read_text(encoding="utf-8")
_CLASSIFY_PROMPT_TEMPLATE = (_PROMPTS_DIR / "classify.md").read_text(encoding="utf-8")
_QA_PROMPT_TEMPLATE = (_PROMPTS_DIR / "qa.md").read_text(encoding="utf-8")
_COMPOSE_ANSWER_TEMPLATE = (_PROMPTS_DIR / "compose_answer.md").read_text(encoding="utf-8")
_RESOLVE_VERSION_TEMPLATE = (_PROMPTS_DIR / "resolve_version.md").read_text(encoding="utf-8")
_EXTRACT_PROFILE_TEMPLATE = (_PROMPTS_DIR / "extract_profile.md").read_text(encoding="utf-8")

# Used verbatim, not formatted: the message being summarised or titled is sent
# as a separate HumanMessage rather than interpolated, so neither has a
# ``load_*`` counterpart.
SESSION_TITLE_PROMPT = (_PROMPTS_DIR / "session_title.md").read_text(encoding="utf-8")
SESSION_SUMMARY_PROMPT = (_PROMPTS_DIR / "session_summary.md").read_text(encoding="utf-8")

_NO_MEMORY = "# What you know about this user\n\nNothing recorded yet."
# Deliberately says "none available" rather than "this user has none": callers
# that withhold episodic context on purpose (``_compose_answer``) render this
# block too, and a model told the user has no history will eventually say so.
_NO_EPISODES = "# Earlier conversations\n\nNone available for this turn."


def load_system_prompt(
    username: str | None = None, semantic_context: str = "", episodic_context: str = ""
) -> str:
    """Render the shared system prompt.

    The two memory blocks are rendered under separate headings on purpose. One
    holds standing facts with no time attached, the other holds dated accounts
    of past conversations, and a model given them as one list will happily
    report a thing that was true in March as a thing that is true now.

    Args:
        username: Display name of the authenticated user, if known.
        semantic_context: What is known about this user, rendered from their
            stored profile. Empty when nothing is, or the user is anonymous.
        episodic_context: Summaries of this user's earlier sessions, newest
            first. Empty when there are none, or the user is anonymous.

    Returns:
        The formatted system prompt.
    """
    user_context = f"# User\n\nYou are talking to {username}.\n" if username else ""
    memory_block = (
        f"# What you know about this user\n\n{semantic_context}" if semantic_context else _NO_MEMORY
    )
    episodic_block = (
        f"# Earlier conversations\n\n{episodic_context}" if episodic_context else _NO_EPISODES
    )
    return _SYSTEM_PROMPT_TEMPLATE.format(
        agent_name=f"{settings.PROJECT_NAME} Agent",
        current_date_and_time=datetime.now(UTC).strftime("%Y-%m-%d %H:%M:%S UTC"),
        user_context=user_context,
        semantic_context=memory_block,
        episodic_context=episodic_block,
    )


def load_classify_prompt(conversation: str) -> str:
    """Render the intent-classifier prompt.

    Args:
        conversation: Recent turns, formatted one ``role: content`` per line.

    Returns:
        The formatted classifier prompt.
    """
    return _CLASSIFY_PROMPT_TEMPLATE.format(conversation=conversation)


def load_extract_profile_prompt(conversation: str) -> str:
    """Render the profile-extraction prompt.

    Args:
        conversation: Recent turns, formatted one ``role: content`` per line.

    Returns:
        The formatted extraction prompt.
    """
    return _EXTRACT_PROFILE_TEMPLATE.format(conversation=conversation)


def load_qa_prompt(
    plan_context: str, semantic_context: str = "", episodic_context: str = ""
) -> str:
    """Render the general-knowledge answering prompt.

    Args:
        plan_context: Read-only summary of the user's current plan and macros,
            used to personalise the answer. Empty when they have no plan.
        semantic_context: What is known about this user, rendered from their
            profile *after* this turn's facts were merged into it — the agent
            never looks anything up about the user for itself.
        episodic_context: Earlier sessions, loaded once per turn for the same
            reason. Empty when there are none.

    Returns:
        The formatted QA prompt.
    """
    return _QA_PROMPT_TEMPLATE.format(
        plan_context=plan_context or "The user has no saved plan.",
        semantic_context=semantic_context or "Nothing recorded about this user yet.",
        episodic_context=episodic_context or "No earlier conversations with this user.",
    )


def load_compose_answer_prompt(
    verdict: str, plan: str, macros: str, issues: str, status: str
) -> str:
    """Render the answer-composition prompt.

    Every argument is pre-rendered text rather than an object, so the node
    decides what the model sees and the model cannot reach a field that was not
    deliberately handed to it.

    Args:
        verdict: ``pass``, ``warn`` or ``fail``.
        plan: The plan, rendered day by day.
        macros: The nutrition targets.
        issues: The findings, most severe first.
        status: Whether the plan below was produced this turn or is the one the
            user already had. Decided in code, because the model cannot tell the
            two apart from the plan text and the difference is the whole meaning
            of the answer.

    Returns:
        The formatted prompt.
    """
    return _COMPOSE_ANSWER_TEMPLATE.format(
        verdict=verdict, plan=plan, macros=macros, issues=issues, status=status
    )


def load_resolve_version_prompt(versions: str, query: str) -> str:
    """Render the version-resolution prompt.

    Args:
        versions: The user's version index, newest first, one per line.
        query: What the user said.

    Returns:
        The formatted prompt.
    """
    return _RESOLVE_VERSION_TEMPLATE.format(versions=versions, query=query)


__all__ = [
    "SESSION_SUMMARY_PROMPT",
    "SESSION_TITLE_PROMPT",
    "load_classify_prompt",
    "load_compose_answer_prompt",
    "load_extract_profile_prompt",
    "load_qa_prompt",
    "load_resolve_version_prompt",
    "load_system_prompt",
]
