"""Prompts owned by the ingest agent, read once at import."""

from pathlib import Path

_PROMPTS_DIR = Path(__file__).parent

_PARSE_PLAN_TEMPLATE = (_PROMPTS_DIR / "parse_plan.md").read_text(encoding="utf-8")


def load_parse_plan_prompt(conversation: str) -> str:
    """Render the plan-parsing prompt.

    Args:
        conversation: Recent turns, one ``role: content`` per line.

    Returns:
        The formatted prompt.
    """
    return _PARSE_PLAN_TEMPLATE.format(conversation=conversation)


__all__ = ["load_parse_plan_prompt"]
