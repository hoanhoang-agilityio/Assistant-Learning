"""Rendering plans, findings and profiles as text for prompts and answers.

One module rather than a private helper in each agent, because these are the
strings a model is allowed to see. Under a supervisor the same plan is described
by three different callers — the planning agent's draft envelope, the review
agent's report and the supervisor's own prose — and three renderers would drift
until the same plan read as two different plans depending on which tool produced
it.

Everything here takes data and returns text. Nothing here reads state, and
nothing takes a model: a renderer that could call an LLM would be a place for a
number to change on its way to the page.
"""

import json
from typing import Any

from app.models.exercise import UNIT_SECONDS
from app.schemas.graph import Issue
from app.services.catalog import load_catalog
from app.services.templates import get_template

# How a stored profile field is named to a model. Separate from ``FIELD_LABELS``
# in ``app/services/profile.py``, which phrases the same columns as questions to
# ask the user — "your height (cm)" reads as an interrogation when it appears in
# a list of things already known.
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


def render_prescription(exercise: dict[str, Any], catalog: dict[str, dict]) -> str:
    """Render one exercise's sets and either its reps or its hold time.

    The plan stores the slot's rep range verbatim — ``commit_draft`` asserts it
    still equals the template's — so the unit cannot be read from the plan. It
    is a property of the movement, and it is looked up here rather than copied
    into the plan so that stored plans render correctly without a backfill.

    Args:
        exercise: One entry from a day's ``exercises``.
        catalog: The exercise catalog, keyed by id.

    Returns:
        The prescription as text, e.g. ``4 sets x 6-8 reps, RIR 1-2`` or
        ``3 sets x 30-60 seconds, RIR 1-2``.
    """
    reps = exercise["reps"]
    rir = exercise["rir"]
    entry = catalog.get(exercise.get("exercise_id") or "") or {}
    duration = entry.get("duration_seconds")

    # Falls back to reps for anything the catalog no longer holds — a retired
    # exercise in an old plan renders as it always did rather than raising.
    if entry.get("unit") == UNIT_SECONDS and duration:
        measure = f"{duration[0]}-{duration[1]} seconds"
    else:
        measure = f"{reps[0]}-{reps[1]} reps"

    return f"{exercise['sets']} sets x {measure}, RIR {rir[0]}-{rir[1]}"


def render_plan(plan: dict[str, Any] | None, goal: str | None = None) -> str:
    """Render a plan as compact text.

    The header lines are not decoration. The answer opens with the split, the
    sessions a week and the goal, and a model asked for a fact the data does not
    carry will supply one from somewhere else — long-term memory, or a finding
    that names a day of the plan it replaced. So the three facts that sentence
    needs are stated here, from the plan itself.

    Sessions a week is counted off the plan rather than read from the template
    or the profile, because those are what was *asked for*: a slot with no legal
    exercise leaves a day out, and the count the user is given must be the one
    they will actually train — the same count ``calc_macros`` fed into TDEE.

    Args:
        plan: The plan to render.
        goal: The goal its macros were computed for, when known.

    Returns:
        A three-line header, then one line per exercise grouped by day. A
        placeholder when there is no plan, so the model is never handed an empty
        section it might fill in.
    """
    if not plan or not plan.get("days"):
        return "No plan could be produced."

    template = get_template(plan.get("template_id") or "")
    lines: list[str] = [
        # A pasted plan has no template, and inventing a split name for it would
        # be the same failure this header exists to prevent.
        f"Split: {template['name'] if template else 'not from a template library'}",
        f"Sessions a week: {len(plan['days'])}",
        f"Goal: {goal or 'not stated'}",
        "",
    ]
    # Numbered, and separated by a blank line. A bare `Chest:` line is what the
    # composer ran together with the previous day's last exercise, producing an
    # answer that read as one long chest session; an ordinal the model has to
    # carry through makes two days impossible to merge into one heading.
    catalog = load_catalog()
    for index, day in enumerate(plan["days"], start=1):
        lines.append(f"Day {index} — {day['name']}:")
        for exercise in day["exercises"]:
            lines.append(f"  - {exercise['name']}: {render_prescription(exercise, catalog)}")
        lines.append("")
    return "\n".join(lines).rstrip()


def render_issues(issues: list[Issue]) -> str:
    """Render findings, most severe first.

    Args:
        issues: Already-sorted findings.

    Returns:
        One line per finding, including its rubric reference so the answer can
        be traced back to the rule that produced it.
    """
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
    """Render the user's plan and macros as read-only text for a prompt.

    Args:
        plan: The approved plan, if any.
        macros: Macros belonging to that plan, if any.

    Returns:
        A compact summary, or an empty string when the user has no plan.
    """
    if not plan and not macros:
        return ""

    parts: list[str] = []
    if plan:
        parts.append(f"Plan: {json.dumps(plan, ensure_ascii=False)}")
    if macros:
        parts.append(f"Macros: {json.dumps(macros, ensure_ascii=False)}")
    return "\n".join(parts)


def render_semantic_context(profile: dict[str, Any]) -> str:
    """Render standing facts about the user as text for a prompt.

    Derived at the point of use rather than carried in state, and that is not an
    optimisation. ``extract_profile`` merges what the user said this turn *after*
    the profile is loaded, so a string rendered at load time would be one turn
    stale — it would still say 68 kg on the turn the user says they are 73. The
    profile itself is the state; this is a view of it.

    ``preferences`` and ``unmapped_injury`` are included: they are the two fields
    that carry the user's own words, and they are the reason a knowledge answer
    can avoid suggesting the movement that hurts.

    Args:
        profile: The merged profile.

    Returns:
        One ``label: value`` per known field, or an empty string when nothing is
        known — the prompt loaders supply their own wording for that case.
    """
    if not profile:
        return ""

    lines: list[str] = []
    for field, value in profile.items():
        if value is None or value == "":
            continue
        # An empty list is an answer, not a blank: `injuries: []` means the user
        # said they have none, and a prompt that omits it invites the model to
        # ask again.
        rendered = (
            (", ".join(str(item) for item in value) or "none")
            if isinstance(value, list)
            else str(value)
        )
        lines.append(f"- {_SEMANTIC_LABELS.get(field, field)}: {rendered}")

    return "\n".join(lines)


__all__ = [
    "render_issues",
    "render_plan",
    "render_plan_context",
    "render_prescription",
    "render_semantic_context",
]
