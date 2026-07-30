"""Small deterministic fitness tools exposed to the Fitness capability."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from core.capabilities.fitness.blueprint import PlanBlueprint, build_plan_blueprint
from core.capabilities.fitness.normalize import (
    explain_verified_plan as _explain_verified_plan_llm,
)
from core.capabilities.fitness.normalize import (
    normalize_submitted_plan,
    qualitative_review_unparseable_plan,
)
from core.capabilities.fitness.planner import generate_structured_workout
from core.capabilities.fitness.template_registry import (
    adapt_workout_to_blueprint,
    resolve_workout_template,
)
from core.capabilities.fitness.utils import (
    calculate_macros_data,
    humanize_safety_feedback,
    load_fitness_context,
    synthesize_plan_data,
    validate_workout_safety_data,
    write_fitness_artifacts,
)
from core.shared.profile.goal_spec import derive_goal_spec
from core.shared.profile.store import load_run_profile, split_constraints
from core.vfs import VFS
from core.vfs.layout import PLAN_SUBMITTED_TEXT


def load_research_result(workspace_path: str) -> dict[str, Any]:
    context = load_fitness_context(workspace_path)
    return {
        "structured_findings": context.get("structured_findings"),
        "evidence_summary": context.get("evidence_summary"),
        "evidence": context.get("evidence") or [],
        "sources": context.get("sources") or [],
    }


def calculate_calories(workspace_path: str) -> dict[str, Any]:
    profile = load_run_profile(workspace_path)
    constraints = split_constraints(profile)
    goal_spec = derive_goal_spec(profile)
    macros = calculate_macros_data(profile, constraints, goal_spec)
    return {"macro_targets": macros["macro_targets"]}


def calculate_macros(workspace_path: str) -> dict[str, Any]:
    return calculate_calories(workspace_path)


def macro_comparison_text(macros: dict[str, Any], reported: dict[str, Any] | None) -> str:
    """Plain-English verdict comparing `reported` calorie/macro figures (either the
    user's own current intake or a submitted plan's stated macro targets) against
    the computed recommended `macros`. Falls back to a plain statement of the
    computed targets when nothing was reported to compare against. Shared by
    `evaluate_macros` (verify_macros) and the merged verify_plan+macros path in
    `executor.py`, so both surfaces render the exact same verdict wording."""
    goal = macros.get("goal", "general_fitness")
    protein = macros["protein_g"]
    calories = macros["calories"]
    target_phrase = (
        f"the recommended {calories} kcal/day target for a {goal} goal "
        f"({protein}g protein, {macros['carbs_g']}g carbs, {macros['fat_g']}g fat)"
    )

    reported_calories = (reported or {}).get("daily_calories")
    if reported_calories is None:
        return (
            f"For a {goal} goal, estimated daily targets are {calories} kcal with "
            f"{protein}g protein, {macros['carbs_g']}g carbs, and {macros['fat_g']}g fat."
        )

    delta = reported_calories - calories
    tolerance = max(round(calories * 0.05), 50)
    if abs(delta) <= tolerance:
        verdict = f"Your {reported_calories} kcal/day is right in line with {target_phrase}."
    elif delta > 0:
        pct = round(delta / calories * 100)
        verdict = (
            f"Your {reported_calories} kcal/day is {delta} kcal ({pct}% over) above {target_phrase}. "
            f"That's more of a maintenance/surplus level than a {goal.replace('_', ' ')} target."
        )
    else:
        pct = round(-delta / calories * 100)
        verdict = (
            f"Your {reported_calories} kcal/day is {-delta} kcal ({pct}% under) below {target_phrase}. "
            "That may be too aggressive a deficit to sustain."
        )

    reported_protein = (reported or {}).get("protein_g")
    if reported_protein is not None:
        protein_delta = reported_protein - protein
        if abs(protein_delta) > max(round(protein * 0.1), 10):
            direction = "above" if protein_delta > 0 else "below"
            verdict += (
                f" Your reported {reported_protein}g protein is also {abs(protein_delta)}g "
                f"{direction} the {protein}g target."
            )

    return verdict


def evaluate_macros(workspace_path: str, reported: dict[str, Any] | None = None) -> dict[str, Any]:
    data = calculate_calories(workspace_path)
    macros = data["macro_targets"]
    assessment = macro_comparison_text(macros, reported)
    return {
        "macro_targets": macros,
        "reported_macros": reported,
        "assessment": assessment,
    }


def generate_blueprint(workspace_path: str) -> dict[str, Any]:
    profile = load_run_profile(workspace_path)
    constraints = split_constraints(profile)
    goal_spec = derive_goal_spec(profile)
    blueprint = build_plan_blueprint(profile, constraints, goal_spec)
    return {"plan_blueprint": blueprint.model_dump(), "goal_spec": goal_spec.model_dump()}


def select_template(workspace_path: str) -> dict[str, Any]:
    context = load_fitness_context(workspace_path)
    profile = context["profile"]
    constraints = context["constraints"]
    blueprint = PlanBlueprint.model_validate(generate_blueprint(workspace_path)["plan_blueprint"])
    resolution = resolve_workout_template(
        workspace_path=workspace_path,
        profile=profile,
        constraints=constraints,
        blueprint=blueprint,
        planner_feedback=[],
        verification_feedback=context.get("verification_feedback"),
        is_verification_rerun=False,
        days_per_week_explicit=False,
        fitness_mode="generate",
    )
    return {
        "template_fingerprint": resolution.get("template_fingerprint"),
        "workout_source": resolution.get("workout_source"),
        "structured_workout": resolution.get("structured_workout"),
    }


def populate_template(workspace_path: str) -> dict[str, Any]:
    context = load_fitness_context(workspace_path)
    profile = context["profile"]
    constraints = context["constraints"]
    macros = calculate_macros_data(profile, constraints, derive_goal_spec(profile))
    blueprint = PlanBlueprint.model_validate(generate_blueprint(workspace_path)["plan_blueprint"])
    workout = generate_structured_workout(
        profile=profile,
        constraints=constraints,
        macro_targets=macros["macro_targets"],
        training_constraints=macros["training_constraints"],
        execution_plan=context.get("execution_plan"),
        structured_findings=context.get("structured_findings"),
        evidence=context.get("evidence") or [],
        planner_feedback=[],
        verification_feedback=context.get("verification_feedback"),
        mode="generate",
    )
    adapted = adapt_workout_to_blueprint(workout.model_dump(), blueprint)
    return {"structured_workout": adapted}


def validate_plan(workspace_path: str, structured_workout: dict[str, Any]) -> dict[str, Any]:
    profile = load_run_profile(workspace_path)
    constraints = split_constraints(profile)
    goal_spec = derive_goal_spec(profile)
    macros = calculate_macros_data(profile, constraints, goal_spec)
    return validate_workout_safety_data(
        profile=profile,
        macro_targets=macros["macro_targets"],
        training_constraints=macros["training_constraints"],
        structured_workout=structured_workout,
    )


def render_plan(
    workspace_path: str,
    *,
    macro_targets: dict[str, Any],
    structured_workout: dict[str, Any],
    plan_blueprint: dict[str, Any],
) -> dict[str, Any]:
    from core.capabilities.fitness.planner import resolve_grounded_claims_for_render
    from core.shared.grounding.render import (
        render_grounded_claims_json,
        render_grounded_claims_markdown,
    )

    context = load_fitness_context(workspace_path)
    claims = resolve_grounded_claims_for_render(
        structured_workout=structured_workout,
        structured_findings=context.get("structured_findings"),
        evidence=context.get("evidence") or [],
    )
    grounded_markdown = render_grounded_claims_markdown(claims)
    grounded_json = render_grounded_claims_json(claims)
    synthesized = synthesize_plan_data(
        macro_targets=macro_targets,
        structured_workout=structured_workout,
        evidence_summary=None,
        verification_feedback=None,
        safety_result={"passed": True, "feedback": []},
        plan_blueprint=plan_blueprint,
        grounded_claims_markdown=grounded_markdown,
    )
    return {
        "draft_plan": synthesized["draft_plan"],
        "grounded_claims_markdown": grounded_markdown,
        "grounded_claims_json": grounded_json,
    }


def write_artifacts(
    workspace_path: str,
    *,
    macro_targets: dict[str, Any],
    structured_workout: dict[str, Any],
    draft_plan: str,
    plan_blueprint: dict[str, Any],
    safety_result: dict[str, Any],
    correlation_id: str,
    grounded_claims_markdown: str | None = None,
    grounded_claims_json: dict[str, Any] | None = None,
) -> dict[str, Any]:
    fingerprint_path = Path(workspace_path) / "fitness" / f".write_{correlation_id}.done"
    if fingerprint_path.exists():
        return {"written": False, "reason": "idempotent_skip"}
    write_fitness_artifacts(
        workspace_path=workspace_path,
        macro_targets=macro_targets,
        structured_workout=structured_workout,
        draft_plan=draft_plan,
        safety_result=safety_result,
        plan_blueprint=plan_blueprint,
        grounded_claims_markdown=grounded_claims_markdown,
        grounded_claims_json=grounded_claims_json,
    )
    fingerprint_path.parent.mkdir(parents=True, exist_ok=True)
    fingerprint_path.write_text("done", encoding="utf-8")
    return {"written": True}


def normalize_submitted(workspace_path: str, submitted_text: str) -> dict[str, Any]:
    profile = load_run_profile(workspace_path)
    constraints = split_constraints(profile)
    goal_spec = derive_goal_spec(profile)
    macros = calculate_macros_data(profile, constraints, goal_spec)
    result = normalize_submitted_plan(submitted_text, macros["training_constraints"])
    return {
        "structured_workout": result["structured_workout"],
        "findings": result["normalization_findings"],
    }


def load_submitted_plan_text(workspace_path: str) -> str:
    """Read the persisted submitted-plan text from VFS.

    Fallback for `verify_plan` when the orchestration state's own `submitted_plan_text`
    field is empty (e.g. an older checkpoint) -- VFS is the durable copy written once at
    Supervisor classification time (`core/agents/supervisor.py`) and at run creation
    (`core/graph/run.py:create_initial_state`), so it outlives any individual state snapshot.
    """
    vfs = VFS.for_run(Path(workspace_path))
    if not vfs.exists(PLAN_SUBMITTED_TEXT):
        return ""
    return vfs.read(PLAN_SUBMITTED_TEXT)


def qualitative_review_submitted_plan(submitted_plan_text: str) -> str:
    return qualitative_review_unparseable_plan(submitted_plan_text)


def _format_verification_context(
    *,
    goal: str,
    goal_archetype: str,
    macro_targets: dict[str, Any] | None,
    structured_workout: dict[str, Any],
    safety: dict[str, Any],
    reported_macros: dict[str, Any] | None = None,
) -> str:
    lines = [f"Goal: {goal} (archetype: {goal_archetype})"]
    if macro_targets:
        lines.append(
            f"Macro targets: {macro_targets['calories']} kcal/day, "
            f"{macro_targets['protein_g']}g protein, {macro_targets['carbs_g']}g carbs, "
            f"{macro_targets['fat_g']}g fat."
        )
    else:
        lines.append("Macro targets: not available (profile missing weight/height/age).")
    if macro_targets and reported_macros and any(v is not None for v in reported_macros.values()):
        # The plan itself stated (or the user separately reported) macro numbers -- fold the
        # same delta verdict verify_macros would give into this one context, so the LLM
        # narrative below addresses macro fit alongside training fit instead of the caller
        # having to stitch two separate responses together.
        lines.append(f"Macro comparison: {macro_comparison_text(macro_targets, reported_macros)}")
    lines.append(f"Training days/week: {len(structured_workout.get('days', []))}")
    lines.append(f"Weekly sets (computed from the plan): {structured_workout.get('weekly_sets')}")
    lines.append("Plan:")
    for day in structured_workout.get("days", []):
        exercise_line = ", ".join(
            f"{exercise['name']} {exercise['sets']}x{exercise['reps']}"
            for exercise in day.get("exercises", [])
        )
        lines.append(f"- {day.get('name')} ({day.get('focus')}): {exercise_line}")
    passed = safety.get("passed", False)
    lines.append(f"Deterministic safety check: {'PASSED' if passed else 'FAILED'}")
    readable_findings = humanize_safety_feedback(safety.get("feedback") or [])
    if readable_findings:
        lines.append("Safety findings:")
        for finding in readable_findings:
            lines.append(f"- {finding}")
    notes = safety.get("notes") or []
    if notes:
        lines.append("Notes:")
        for note in notes:
            lines.append(f"- {note}")
    return "\n".join(lines)


def explain_verified_plan(
    workspace_path: str,
    structured_workout: dict[str, Any],
    safety: dict[str, Any],
    reported_macros: dict[str, Any] | None = None,
) -> str:
    """Turn a completed verify_plan safety check into a user-facing natural-language summary
    (goal fit, volume/exercise-selection adequacy, sets/reps/frequency, weaknesses with
    concrete suggestions) instead of the bare pass/fail/feedback-code result.

    `reported_macros` is optional: pass it when the submitted text also stated macro/
    calorie numbers to check (the plan's own targets, or the user's reported intake) --
    the explanation then covers macro fit alongside training fit in one narrative,
    instead of the caller needing a second, separate verify_macros response."""
    profile = load_run_profile(workspace_path)
    constraints = split_constraints(profile)
    goal_spec = derive_goal_spec(profile)
    macros = calculate_macros_data(profile, constraints, goal_spec)
    context = _format_verification_context(
        goal=str(profile.get("goal", "general_fitness")),
        goal_archetype=goal_spec.goal_archetype,
        macro_targets=macros["macro_targets"],
        structured_workout=structured_workout,
        safety=safety,
        reported_macros=reported_macros,
    )
    return _explain_verified_plan_llm(context)
