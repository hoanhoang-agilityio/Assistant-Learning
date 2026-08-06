"""Prompts owned by the profile agent, read once at import."""

from pathlib import Path

_PROMPTS_DIR = Path(__file__).parent

_EXTRACT_PROFILE_TEMPLATE = (_PROMPTS_DIR / "extract_profile.md").read_text(encoding="utf-8")


def load_extract_profile_prompt(conversation: str) -> str:
    """Render the profile-extraction prompt.

    Args:
        conversation: Recent turns, one ``role: content`` per line.

    Returns:
        The formatted prompt.
    """
    return _EXTRACT_PROFILE_TEMPLATE.format(conversation=conversation)


__all__ = ["load_extract_profile_prompt"]
