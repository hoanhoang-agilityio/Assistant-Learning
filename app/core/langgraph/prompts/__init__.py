"""Shared prompt templates, read from disk once at import.

Every prompt is a ``.md`` file next to this module so it is reviewable in a diff.
The files are read at import time and only formatted per call — a node that
opens a file on every request pays disk I/O inside the event loop.

Templates use ``str.format``, so any literal brace in a prompt body must be
doubled (``{{`` / ``}}``).
"""

from pathlib import Path

from app.core.langgraph.supervisor.prompts import (
    load_classify_prompt,
    load_extract_profile_prompt,
)

_PROMPTS_DIR = Path(__file__).parent

# Used verbatim, not formatted: the message being summarised or titled is sent
# as a separate HumanMessage rather than interpolated, so neither has a
# ``load_*`` counterpart.
SESSION_TITLE_PROMPT = (_PROMPTS_DIR / "session_title.md").read_text(encoding="utf-8")
SESSION_SUMMARY_PROMPT = (_PROMPTS_DIR / "session_summary.md").read_text(encoding="utf-8")

__all__ = [
    "SESSION_SUMMARY_PROMPT",
    "SESSION_TITLE_PROMPT",
    "load_classify_prompt",
    "load_extract_profile_prompt",
]
