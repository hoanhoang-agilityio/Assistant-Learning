"""Render supervisor-owned profile context for prompts."""

from typing import Any

from app.utils.sanitization import sanitize_prompt_text

# The fields with no controlled vocabulary behind them. Only these get their
# markup stripped: the rest are tokens whose underscores are part of the value,
# and `very_active` rendered as `veryactive` is a fact quietly corrupted.
_FREE_TEXT_FIELDS = frozenset({"preferences", "unmapped_injury"})

# A backstop, not the real bound — `clean_extraction` and `merge_preferences`
# bound these fields on the way in. This one covers rows those two never saw:
# written before they existed, or by some later caller. Generous enough that a
# legitimately accumulated column is never truncated here.
_MAX_FREE_TEXT = 2000

_SEMANTIC_LABELS: dict[str, str] = {
    "weight_kg": "Body weight (kg)",
    "height_cm": "Height (cm)",
    "age": "Age",
    "sex": "Sex",
    "activity_level": "Daily activity outside training",
    "days_per_week": "Training days per week",
    "level": "Training experience (1 new – 5 advanced)",
    "goal": "Goal",
    "equipment": "Equipment available",
    "injuries": "Injuries screened by the rubric",
    "preferences": "Stated preferences",
    "unmapped_injury": "Injury described but not in the rubric",
}


def render_semantic_context(profile: dict[str, Any]) -> str:
    """Render standing facts about the user as text for a prompt.

    This is where the profile enters the supervisor's **system** message, so it
    is the last place a stored value can be stopped from reading as an
    instruction. Every value is flattened to one line — the list is
    newline-separated, so a value carrying its own newline writes a bullet the
    profile never had — and the free-text fields also lose their markup.

    Deliberately does not trust its caller. ``clean_extraction`` already does
    this on the way in; doing it again costs nothing and is what makes a row
    written by an older version, or by a path that skips the extractor, safe to
    render.

    Args:
        profile: The profile as this turn holds it.

    Returns:
        One ``- Label: value`` line per answered field, or an empty string.
    """
    if not profile:
        return ""
    lines: list[str] = []
    for field, value in profile.items():
        if value is None or value == "":
            continue
        rendered = (
            (", ".join(str(item) for item in value) or "none")
            if isinstance(value, list)
            else str(value)
        )
        rendered = (
            sanitize_prompt_text(rendered, _MAX_FREE_TEXT)
            if field in _FREE_TEXT_FIELDS
            else " ".join(rendered.split())
        )
        if not rendered:
            continue
        lines.append(f"- {_SEMANTIC_LABELS.get(field, field)}: {rendered}")
    return "\n".join(lines)


__all__ = ["render_semantic_context"]
