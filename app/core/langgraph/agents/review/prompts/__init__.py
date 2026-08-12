"""Prompts owned by the review agent, read once at import."""

from pathlib import Path

_PROMPTS_DIR = Path(__file__).parent

_REVIEW_AGENT_TEMPLATE = (_PROMPTS_DIR / "review_agent.md").read_text(encoding="utf-8")


def load_review_agent_prompt() -> str:
    """Render the review agent's system prompt."""
    return _REVIEW_AGENT_TEMPLATE


__all__ = ["load_review_agent_prompt"]
