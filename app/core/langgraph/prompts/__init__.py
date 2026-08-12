"""Shared prompt templates, read from disk once at import.

Every prompt is a ``.md`` file next to this module so it is reviewable in a diff.
The files are read at import time and only formatted per call — a node that
opens a file on every request pays disk I/O inside the event loop.

Templates use ``str.format``, so any literal brace in a prompt body must be
doubled (``{{`` / ``}}``).
"""

from pathlib import Path

_PROMPTS_DIR = Path(__file__).parent

_CLASSIFY_PROMPT_TEMPLATE = (_PROMPTS_DIR / "classify.md").read_text(encoding="utf-8")
_EXTRACT_PROFILE_TEMPLATE = (_PROMPTS_DIR / "extract_profile.md").read_text(encoding="utf-8")

# Used verbatim, not formatted: the message being summarised or titled is sent
# as a separate HumanMessage rather than interpolated, so neither has a
# ``load_*`` counterpart.
SESSION_TITLE_PROMPT = (_PROMPTS_DIR / "session_title.md").read_text(encoding="utf-8")
SESSION_SUMMARY_PROMPT = (_PROMPTS_DIR / "session_summary.md").read_text(encoding="utf-8")


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


__all__ = [
    "SESSION_SUMMARY_PROMPT",
    "SESSION_TITLE_PROMPT",
    "load_classify_prompt",
    "load_extract_profile_prompt",
]
