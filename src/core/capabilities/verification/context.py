"""Loading everything verification needs to judge a run, out of the run VFS."""

import json
from pathlib import Path
from typing import Any

from core.adapters.llm.serializers import compact_evidence_for_llm
from core.adapters.vfs import VFS
from core.capabilities.fitness.utils import build_workout_summary


def load_verification_context(workspace_path: str) -> dict[str, Any]:
    vfs = VFS.for_run(Path(workspace_path))
    draft_plan = ""
    grounded_claims = ""
    sources: list[dict[str, Any]] = []
    evidence: list[dict[str, Any]] = []
    macro_targets: dict[str, Any] = {}
    training_plan: dict[str, Any] = {}
    safety_flags: list[str] = []
    fitness_safety_passed: bool | None = None

    if vfs.exists("fitness/final_plan.md"):
        draft_plan = vfs.read("fitness/final_plan.md")
    if vfs.exists("fitness/grounded_claims.md"):
        grounded_claims = vfs.read("fitness/grounded_claims.md")
    if vfs.exists("research/sources.json"):
        sources = json.loads(vfs.read("research/sources.json"))
    if vfs.exists("research/findings.json"):
        findings = json.loads(vfs.read("research/findings.json"))
        evidence = compact_evidence_for_llm(findings.get("evidence", []))
    if vfs.exists("fitness/workout.json"):
        structured_workout = json.loads(vfs.read("fitness/workout.json"))
        training_plan = build_workout_summary(structured_workout)
    if vfs.exists("fitness/calculations.json"):
        calculations = json.loads(vfs.read("fitness/calculations.json"))
        macro_targets = calculations.get("macro_targets", {})
        if not training_plan:
            training_plan = calculations.get("workout_summary") or calculations.get(
                "training_plan_summary", {}
            )
    if vfs.exists("fitness/safety_flags.json"):
        safety_flags = json.loads(vfs.read("fitness/safety_flags.json"))
    if vfs.exists("fitness/safety_passed.json"):
        fitness_safety_passed = json.loads(vfs.read("fitness/safety_passed.json"))
    blueprint: dict[str, Any] = {}
    if vfs.exists("fitness/blueprint.json"):
        blueprint = json.loads(vfs.read("fitness/blueprint.json"))

    return {
        "draft_plan": draft_plan,
        "grounded_claims": grounded_claims,
        "sources": sources,
        "evidence": evidence,
        "macro_targets": macro_targets,
        "training_plan": training_plan,
        "safety_flags": safety_flags,
        "plan_blueprint": blueprint,
        "fitness_safety_passed": fitness_safety_passed,
    }
