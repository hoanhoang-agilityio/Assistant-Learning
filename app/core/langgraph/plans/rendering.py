"""Rendering plans, findings and profiles as text for prompts and answers."""

import json
from typing import Any

from app.core.langgraph.supervisor.prompt_context import render_semantic_context
from app.models.exercise import UNIT_SECONDS
from app.schemas.graph import Issue
from app.services.catalog import load_catalog
from app.services.templates import get_template


def render_prescription(exercise: dict[str, Any], catalog: dict[str, dict]) -> str:
    """Render one exercise's sets and either its reps or its hold time."""
    reps = exercise["reps"]
    rir = exercise["rir"]
    entry = catalog.get(exercise.get("exercise_id") or "") or {}
    duration = entry.get("duration_seconds")
    if entry.get("unit") == UNIT_SECONDS and duration:
        measure = f"{duration[0]}-{duration[1]} seconds"
    else:
        measure = f"{reps[0]}-{reps[1]} reps"
    return f"{exercise['sets']} sets x {measure}, RIR {rir[0]}-{rir[1]}"


def render_plan(plan: dict[str, Any] | None, goal: str | None = None) -> str:
    """Render a plan as compact text."""
    if not plan or not plan.get("days"):
        return "No plan could be produced."
    template = get_template(plan.get("template_id") or "")
    lines: list[str] = [
        f"Split: {template['name'] if template else 'not from a template library'}",
        f"Sessions a week: {len(plan['days'])}",
        f"Goal: {goal or 'not stated'}",
        "",
    ]
    catalog = load_catalog()
    for index, day in enumerate(plan["days"], start=1):
        lines.append(f"{_day_heading(index, day['name'])}:")
        for exercise in day["exercises"]:
            lines.append(f"  - {exercise['name']}: {render_prescription(exercise, catalog)}")
        lines.append("")
    return "\n".join(lines).rstrip()


def _day_heading(index: int, name: str) -> str:
    """Number a day, unless its name already carries the number.

    Built plans take their day names from the template — "Upper A", "Full Body" —
    and need the count in front. A pasted plan takes them from the user, who
    usually wrote "Day 1 — Upper" themselves, and prefixing that produced
    "Day 1 — Day 1 — Upper" in the review.

    Args:
        index: The day's position in the plan, from 1.
        name: The day's name as the plan carries it.

    Returns:
        The heading, without its trailing colon.
    """
    if name.strip().lower().startswith("day "):
        return name.strip()
    return f"Day {index} — {name}"


def render_issues(issues: list[Issue]) -> str:
    """Render findings, most severe first."""
    if not issues:
        return "No findings. Every enabled check passed."
    return "\n".join(
        f"- [{issue['severity']}] {issue['location']}: {issue['message']}"
        + (
            f" Suggested: {json.dumps(issue['suggestion'], ensure_ascii=False)}"
            if issue["suggestion"]
            else ""
        )
        + f" (rule: {issue['rubric_ref']})"
        for issue in issues
    )


def render_plan_context(plan: dict[str, Any] | None, macros: dict[str, Any] | None) -> str:
    """Render the user's plan and macros as read-only text for a prompt."""
    if not plan and not macros:
        return ""
    parts: list[str] = []
    if plan:
        parts.append(f"Plan: {json.dumps(plan, ensure_ascii=False)}")
    if macros:
        parts.append(f"Macros: {json.dumps(macros, ensure_ascii=False)}")
    return "\n".join(parts)


__all__ = [
    "render_issues",
    "render_plan",
    "render_plan_context",
    "render_prescription",
    "render_semantic_context",
]
