"""Persisting fitness results into the run VFS."""

import json
from pathlib import Path
from typing import Any

from core.subgraphs.fitness.synthesis import build_workout_summary
from core.vfs import VFS


def write_fitness_artifacts(
    workspace_path: str,
    macro_targets: dict[str, Any],
    structured_workout: dict[str, Any],
    draft_plan: str,
    safety_result: dict[str, Any],
    plan_blueprint: dict[str, Any] | None = None,
    template_fingerprint: str | None = None,
    workout_source: str | None = None,
    normalization_findings: list[str] | None = None,
    grounded_claims_markdown: str | None = None,
    grounded_claims_json: dict[str, Any] | None = None,
) -> None:
    vfs = VFS.for_run(Path(workspace_path))
    workout_summary = build_workout_summary(structured_workout)
    calculations = {
        "macro_targets": macro_targets,
        "workout_summary": workout_summary,
        "training_plan_summary": workout_summary,
    }
    if plan_blueprint is not None:
        calculations["plan_blueprint"] = plan_blueprint
    vfs.write("fitness/workout.json", json.dumps(structured_workout, indent=2))
    vfs.write("fitness/calculations.json", json.dumps(calculations, indent=2))
    if plan_blueprint is not None:
        vfs.write("fitness/blueprint.json", json.dumps(plan_blueprint, indent=2))
    if template_fingerprint is not None:
        vfs.write(
            "fitness/template_fingerprint.json",
            json.dumps(
                {
                    "fingerprint": template_fingerprint,
                    "workout_source": workout_source,
                },
                indent=2,
            ),
        )
    safety_feedback = safety_result.get("feedback") or []
    vfs.write("fitness/safety_flags.json", json.dumps(safety_feedback, indent=2))
    # The feedback strings above are only the 4-flag allowlist Verification's
    # safety_check_data historically re-derived from -- the actual pass/fail
    # boolean validate_workout_safety_data computed (covering every flag it
    # can emit, not just that subset) was never persisted anywhere, so an
    # equipment mismatch, duplicate exercise, or invalid set count could pass
    # Verification's safety gate silently. Persist it directly.
    vfs.write("fitness/safety_passed.json", json.dumps(safety_result["passed"]))
    vfs.write(
        "fitness/normalization_findings.json",
        json.dumps(normalization_findings or [], indent=2),
    )
    if grounded_claims_json is not None:
        vfs.write("fitness/grounded_claims.json", json.dumps(grounded_claims_json, indent=2))
    if grounded_claims_markdown is not None:
        vfs.write("fitness/grounded_claims.md", grounded_claims_markdown)
    vfs.write("fitness/final_plan.md", draft_plan)
