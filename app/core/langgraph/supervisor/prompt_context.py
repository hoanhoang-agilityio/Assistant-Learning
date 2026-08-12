"""Render supervisor-owned profile context for prompts."""

from typing import Any

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
    """Render standing facts about the user as text for a prompt."""
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
        lines.append(f"- {_SEMANTIC_LABELS.get(field, field)}: {rendered}")
    return "\n".join(lines)


__all__ = ["render_semantic_context"]
