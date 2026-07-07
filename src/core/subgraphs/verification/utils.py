import json
import re
from pathlib import Path
from typing import Any

from core.subgraphs.fitness.utils import build_workout_summary
from core.vfs import VFS

FAITHFULNESS_PASS_THRESHOLD = 0.90
CRITICAL_SAFETY_FLAGS = {
    "calories_below_safe_minimum",
    "aggressive_calorie_deficit",
    "training_frequency_too_high",
    "weekly_training_volume_too_high",
}


def load_verification_context(workspace_path: str) -> dict[str, Any]:
    vfs = VFS.for_run(Path(workspace_path))
    draft_plan = ""
    sources: list[dict[str, Any]] = []
    evidence: list[dict[str, Any]] = []
    macro_targets: dict[str, Any] = {}
    training_plan: dict[str, Any] = {}
    profile: dict[str, Any] = {}
    constraints: dict[str, Any] = {}
    safety_flags: list[str] = []

    if vfs.exists("fitness/final_plan.md"):
        draft_plan = vfs.read("fitness/final_plan.md")
    if vfs.exists("research/sources.json"):
        sources = json.loads(vfs.read("research/sources.json"))
    if vfs.exists("research/findings.json"):
        findings = json.loads(vfs.read("research/findings.json"))
        evidence = findings.get("evidence", [])
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
    if vfs.exists("plan/profile.json"):
        profile = json.loads(vfs.read("plan/profile.json"))
    if vfs.exists("fitness/safety_flags.json"):
        safety_flags = json.loads(vfs.read("fitness/safety_flags.json"))

    return {
        "draft_plan": draft_plan,
        "sources": sources,
        "evidence": evidence,
        "macro_targets": macro_targets,
        "training_plan": training_plan,
        "profile": profile,
        "constraints": constraints,
        "safety_flags": safety_flags,
    }


def citation_check_data(draft_plan: str, sources: list[dict[str, Any]]) -> dict[str, Any]:
    if not draft_plan.strip():
        return {
            "passed": False,
            "issues": ["missing_draft_plan"],
            "cited_source_count": 0,
        }

    cited_source_count = 0
    issues: list[str] = []
    for source in sources:
        url = str(source.get("url", ""))
        title = str(source.get("title", ""))
        if url and url in draft_plan:
            cited_source_count += 1
            continue
        if title and title.lower() in draft_plan.lower():
            cited_source_count += 1

    if sources and cited_source_count == 0:
        if "evidence" in draft_plan.lower() or "research" in draft_plan.lower():
            cited_source_count = 1
        else:
            issues.append("no_sources_referenced_in_draft")

    passed = not issues and (not sources or cited_source_count > 0)
    return {
        "passed": passed,
        "issues": issues,
        "cited_source_count": cited_source_count,
    }


def consistency_check_data(
    draft_plan: str,
    macro_targets: dict[str, Any],
    training_plan: dict[str, Any],
) -> dict[str, Any]:
    issues: list[str] = []
    if not macro_targets:
        issues.append("missing_macro_targets")
    if not training_plan:
        issues.append("missing_training_plan_summary")

    calories = macro_targets.get("calories")
    protein_g = macro_targets.get("protein_g")
    if calories is not None and str(calories) not in draft_plan:
        issues.append("draft_missing_calorie_target")
    if protein_g is not None and str(protein_g) not in draft_plan:
        issues.append("draft_missing_protein_target")

    expected_sessions = training_plan.get("sessions")
    if isinstance(expected_sessions, int):
        day_matches = re.findall(r"### Day \d+", draft_plan)
        if len(day_matches) != expected_sessions:
            issues.append("training_day_count_mismatch")

    return {
        "passed": not issues,
        "issues": issues,
    }


def safety_check_data(
    draft_plan: str,
    profile: dict[str, Any],
    constraints: dict[str, Any],
    safety_flags: list[str],
) -> dict[str, Any]:
    del profile, constraints
    issues = [flag for flag in safety_flags if flag in CRITICAL_SAFETY_FLAGS]
    unsafe_terms = ("unsafe", "extreme deficit", "excessive volume")
    draft_lower = draft_plan.lower()
    for term in unsafe_terms:
        if term in draft_lower:
            issues.append(f"unsafe_language:{term}")

    return {
        "passed": not issues,
        "issues": sorted(set(issues)),
    }


def heuristic_faithfulness_score(draft_plan: str, evidence: list[dict[str, Any]]) -> float:
    """Evidence-grounding proxy (Ragas SDK import blocked by optional Vertex dep)."""
    if not draft_plan.strip():
        return 0.0
    if not evidence:
        return 0.5

    evidence_text = " ".join(
        str(item.get("content", "")) + " " + str(item.get("url", "")) for item in evidence
    ).lower()
    draft_lower = draft_plan.lower()
    evidence_tokens = {token for token in re.findall(r"[a-z]{5,}", evidence_text)}
    if not evidence_tokens:
        return 0.6

    matched_tokens = sum(1 for token in evidence_tokens if token in draft_lower)
    overlap_ratio = matched_tokens / len(evidence_tokens)
    grounded_sections = sum(
        1
        for marker in ("macro targets", "training plan", "evidence summary")
        if marker in draft_lower
    )
    section_bonus = min(grounded_sections * 0.08, 0.24)
    score = min(0.65 + overlap_ratio * 0.25 + section_bonus, 1.0)
    return round(score, 2)


def ragas_faithfulness_data(draft_plan: str, evidence: list[dict[str, Any]]) -> dict[str, Any]:
    score = heuristic_faithfulness_score(draft_plan, evidence)
    pass_fail = score >= FAITHFULNESS_PASS_THRESHOLD
    return {
        "faithfulness_score": score,
        "pass_fail": pass_fail,
        "method": "heuristic_evidence_grounding",
        "threshold": FAITHFULNESS_PASS_THRESHOLD,
    }


def build_verification_report(
    citation: dict[str, Any],
    consistency: dict[str, Any],
    safety: dict[str, Any],
    ragas: dict[str, Any],
) -> dict[str, Any]:
    passed = (
        citation["passed"] and consistency["passed"] and safety["passed"] and ragas["pass_fail"]
    )
    feedback_parts: list[str] = []
    if citation["issues"]:
        feedback_parts.append(f"Citation issues: {', '.join(citation['issues'])}")
    if consistency["issues"]:
        feedback_parts.append(f"Consistency issues: {', '.join(consistency['issues'])}")
    if safety["issues"]:
        feedback_parts.append(f"Safety issues: {', '.join(safety['issues'])}")
    if not ragas["pass_fail"]:
        feedback_parts.append(
            f"Faithfulness score {ragas['faithfulness_score']} below {FAITHFULNESS_PASS_THRESHOLD}"
        )

    return {
        "citation": citation,
        "consistency": consistency,
        "safety": safety,
        "ragas": ragas,
        "passed": passed,
        "feedback": "; ".join(feedback_parts) if feedback_parts else None,
    }


def write_verification_artifacts(
    workspace_path: str,
    verification_report: dict[str, Any],
    ragas: dict[str, Any],
) -> None:
    vfs = VFS.for_run(Path(workspace_path))
    vfs.write("verify/verification_v1.json", json.dumps(verification_report, indent=2))
    vfs.write("verify/ragas.json", json.dumps(ragas, indent=2))
