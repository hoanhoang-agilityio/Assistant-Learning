"""Assembling the final plan text and its workout summary."""

from typing import Any

from core.subgraphs.fitness.edit_ops import EDIT_FAILED_NOTICE


def synthesize_plan_data(
    macro_targets: dict[str, Any],
    structured_workout: dict[str, Any] | None,
    evidence_summary: str | None,
    verification_feedback: str | None,
    safety_result: dict[str, Any],
    plan_blueprint: dict[str, Any] | None = None,
    edit_failed: bool = False,
    grounded_claims_markdown: str | None = None,
) -> dict[str, Any]:
    if structured_workout is None:
        return {"draft_plan": "# Fitness Plan Draft\n\nWorkout plan unavailable.\n"}

    days_markdown: list[str] = []
    for index, day in enumerate(structured_workout.get("days", []), start=1):
        exercise_lines = "\n".join(
            f"  - {exercise['name']}: {exercise['sets']} x {exercise['reps']}"
            for exercise in day.get("exercises", [])
        )
        days_markdown.append(
            f"### Day {index} — {day['name']}\nFocus: {day['focus']}\n{exercise_lines}"
        )

    progression = structured_workout.get("progression")
    progression_section = ""
    if progression:
        progression_section = f"\n## Progression\n\n{progression}\n"

    substitutions = structured_workout.get("substitutions") or []
    substitutions_section = ""
    if substitutions:
        sub_lines = "\n".join(f"- {item}" for item in substitutions)
        substitutions_section = f"\n## Substitutions\n\n{sub_lines}\n"

    notes = structured_workout.get("notes") or []
    notes_section = ""
    if notes:
        note_lines = "\n".join(f"- {note}" for note in notes)
        notes_section = f"\n## Notes\n\n{note_lines}\n"

    # Evidence sections come only from the deterministic grounded-claims renderer.
    # Never trust free-form evidence_applied strings or LLM-written Evidence Summary.
    del evidence_summary
    evidence_section = ""
    if grounded_claims_markdown and grounded_claims_markdown.strip():
        # Strip the top-level "# Grounded Claims" heading; embed body under the plan.
        body = grounded_claims_markdown.strip()
        if body.startswith("# Grounded Claims"):
            body = body.split("\n", 1)[1].lstrip() if "\n" in body else ""
        if body:
            evidence_section = f"\n{body}\n"

    feedback_section = ""
    if verification_feedback:
        feedback_section = f"\n## Verification Feedback Applied\n\n{verification_feedback}\n"

    safety_section = ""
    safety_feedback = safety_result.get("feedback") or []
    if safety_feedback:
        safety_lines = "\n".join(f"- {item}" for item in safety_feedback)
        safety_section = f"\n## Safety Warnings\n\n{safety_lines}\n"

    blueprint_section = ""
    if plan_blueprint:
        horizon = plan_blueprint.get("horizon_weeks")
        weekly_rate = plan_blueprint.get("weekly_rate_kg")
        blueprint_lines = ["## Program Blueprint", ""]
        if horizon:
            blueprint_lines.append(f"- Horizon: {horizon} weeks")
        if weekly_rate is not None:
            blueprint_lines.append(f"- Target weekly rate: {weekly_rate} kg")
        blueprint_lines.append(f"- Archetype: {plan_blueprint.get('goal_archetype', 'n/a')}")
        phases = plan_blueprint.get("phases") or []
        if phases:
            blueprint_lines.append("- Phases:")
            for phase in phases:
                blueprint_lines.append(
                    f"  - Weeks {phase['week_start']}-{phase['week_end']}: "
                    f"{phase['training_emphasis']} (volume x{phase['volume_modifier']})"
                )
        progression_notes = plan_blueprint.get("progression_notes") or []
        for note in progression_notes:
            blueprint_lines.append(f"- {note}")
        blueprint_section = "\n".join(blueprint_lines) + "\n\n"

    draft_plan = (
        "# Fitness Plan Draft\n\n"
        f"{blueprint_section}"
        "## Macro Targets\n\n"
        f"- Calories: {macro_targets['calories']} kcal\n"
        f"- Protein: {macro_targets['protein_g']} g\n"
        f"- Carbs: {macro_targets['carbs_g']} g\n"
        f"- Fat: {macro_targets['fat_g']} g\n\n"
        "## Training Plan\n\n"
        f"Split: {structured_workout['split']} ({structured_workout['goal']})\n\n"
        f"{chr(10).join(days_markdown)}"
        f"{progression_section}"
        f"{substitutions_section}"
        f"{notes_section}"
        f"{evidence_section}"
        f"{feedback_section}"
        f"{safety_section}"
    )
    if edit_failed:
        draft_plan = draft_plan.replace(
            "# Fitness Plan Draft\n\n", "# Fitness Plan Draft\n\n" + EDIT_FAILED_NOTICE, 1
        )
    return {"draft_plan": draft_plan}


def build_workout_summary(structured_workout: dict[str, Any]) -> dict[str, Any]:
    """Derive a compact workout summary for downstream verification."""
    return {
        "split": structured_workout["split"],
        "goal": structured_workout["goal"],
        "weekly_sets": structured_workout["weekly_sets"],
        "sessions": len(structured_workout.get("days", [])),
    }
