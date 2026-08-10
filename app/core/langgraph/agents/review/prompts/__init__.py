"""Prompts owned by the review agent, read once at import."""

from pathlib import Path

_PROMPTS_DIR = Path(__file__).parent

_REVIEW_AGENT_TEMPLATE = (_PROMPTS_DIR / "review_agent.md").read_text(encoding="utf-8")


def load_review_agent_prompt(profile: str = "") -> str:
    """Render the review agent's system prompt.

    Args:
        profile: The user's standing facts, rendered as text. The macro and
            injury checks read them, so the agent is told what they are — but it
            never looks them up for itself.

    Returns:
        The formatted prompt.
    """
    return _REVIEW_AGENT_TEMPLATE.format(profile=profile or "Nothing recorded about this user yet.")


__all__ = ["load_review_agent_prompt"]
