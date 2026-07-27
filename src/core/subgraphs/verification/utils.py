import json
import re
from pathlib import Path
from typing import Any

from core.llm.serializers import compact_evidence_for_llm
from core.subgraphs.fitness.utils import build_workout_summary
from core.vfs import VFS

FAITHFULNESS_PASS_THRESHOLD = 0.90
CRITICAL_SAFETY_FLAGS = {
    "calories_below_safe_minimum",
    "aggressive_calorie_deficit",
    "training_frequency_too_high",
    "weekly_training_volume_too_high",
}
_SAFETY_SCAN_EXCLUDED_HEADERS = (
    "## Evidence Summary",
    "## Evidence Applied",
    "## Verification Feedback Applied",
    "## Safety Warnings",
    "## Notes",
    "## Program Blueprint",
)


def _draft_text_for_safety_scan(draft_plan: str) -> str:
    """Scan only prescription sections; ignore evidence/feedback metadata in the draft."""
    if not draft_plan.strip():
        return ""
    lines = draft_plan.splitlines()
    scanned_lines: list[str] = []
    include_section = False
    for line in lines:
        if line.startswith("## "):
            include_section = line not in _SAFETY_SCAN_EXCLUDED_HEADERS
        if include_section:
            scanned_lines.append(line)
    if scanned_lines:
        return "\n".join(scanned_lines)
    return draft_plan


def load_verification_context(workspace_path: str) -> dict[str, Any]:
    vfs = VFS.for_run(Path(workspace_path))
    draft_plan = ""
    sources: list[dict[str, Any]] = []
    evidence: list[dict[str, Any]] = []
    macro_targets: dict[str, Any] = {}
    training_plan: dict[str, Any] = {}
    safety_flags: list[str] = []
    fitness_safety_passed: bool | None = None

    if vfs.exists("fitness/final_plan.md"):
        draft_plan = vfs.read("fitness/final_plan.md")
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
        "sources": sources,
        "evidence": evidence,
        "macro_targets": macro_targets,
        "training_plan": training_plan,
        "safety_flags": safety_flags,
        "plan_blueprint": blueprint,
        "fitness_safety_passed": fitness_safety_passed,
    }


def citation_check_data(draft_plan: str, sources: list[dict[str, Any]]) -> dict[str, Any]:
    if not draft_plan.strip():
        return {
            "passed": False,
            "issues": ["missing_draft_plan"],
            "cited_source_count": 0,
        }

    # No sources gathered is a real grounding failure, not "nothing to check" --
    # `not sources` used to make `passed` true unconditionally here, silently
    # rubber-stamping a plan built on zero research evidence.
    if not sources:
        return {
            "passed": False,
            "issues": ["no_sources_gathered"],
            "cited_source_count": 0,
        }

    cited_source_count = 0
    issues: list[str] = []
    for source in sources:
        url = str(source.get("url", ""))
        title = str(source.get("title", ""))
        provider = str(source.get("provider", ""))
        if url and (
            url in draft_plan or (provider == "local_kb" and title.lower() in draft_plan.lower())
        ):
            cited_source_count += 1
            continue
        if title and title.lower() in draft_plan.lower():
            cited_source_count += 1

    # No keyword rubber-stamp: synthesis always emits a "## Evidence Summary"
    # section, so a bare "evidence"/"research" substring match here used to
    # count as citing a source regardless of whether any real source was
    # actually referenced. cited_source_count now only reflects genuine
    # URL/title matches against the sources actually gathered.
    if cited_source_count == 0:
        issues.append("no_sources_referenced_in_draft")

    passed = not issues
    return {
        "passed": passed,
        "issues": issues,
        "cited_source_count": cited_source_count,
    }


def consistency_check_data(
    draft_plan: str,
    macro_targets: dict[str, Any],
    training_plan: dict[str, Any],
    plan_blueprint: dict[str, Any] | None = None,
) -> dict[str, Any]:
    issues: list[str] = []
    if not macro_targets:
        issues.append("missing_macro_targets")
    if not training_plan:
        issues.append("missing_training_plan_summary")
    if plan_blueprint is not None and not plan_blueprint:
        issues.append("missing_plan_blueprint")

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
    safety_flags: list[str],
    *,
    fitness_safety_passed: bool | None = None,
) -> dict[str, Any]:
    """fitness_safety_passed is the actual pass/fail boolean Fitness's own
    validate_workout_safety_data computed (see fitness/utils.py's
    write_fitness_artifacts, which persists it to fitness/safety_passed.json).

    Previously this check only ever re-derived pass/fail from whether any of
    `safety_flags` appeared in the small CRITICAL_SAFETY_FLAGS allowlist below
    -- every other flag Fitness can emit (equipment mismatch, duplicate
    exercise, invalid set count, wrong day count, ...) was silently ignored.
    When fitness_safety_passed is available it's authoritative: any fitness-
    side safety failure blocks delivery, not just the allowlisted subset.
    None (an older workspace predating this field, or a call site that hasn't
    threaded it through) falls back to the flags-only check exactly as before.
    """
    issues = [flag for flag in safety_flags if flag in CRITICAL_SAFETY_FLAGS]
    unsafe_terms = ("unsafe", "extreme deficit", "excessive volume")
    draft_lower = _draft_text_for_safety_scan(draft_plan).lower()
    for term in unsafe_terms:
        if term in draft_lower:
            issues.append(f"unsafe_language:{term}")
    if fitness_safety_passed is False:
        issues.append("fitness_safety_check_failed")

    return {
        "passed": not issues,
        "issues": sorted(set(issues)),
    }


def heuristic_faithfulness_score(draft_plan: str, evidence: list[dict[str, Any]]) -> float:
    """Zero-cost, zero-latency evidence-grounding proxy (token overlap, not entailment).

    Deliberately not Ragas-backed -- see core.evaluation.ragas for the real
    Ragas SDK faithfulness scorer, gated behind
    settings.verification_use_real_ragas and wired only into the benchmark
    script so far (docs/reports/known_limitations_remediation_plan.md, L1).
    """
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


def heuristic_faithfulness_data(draft_plan: str, evidence: list[dict[str, Any]]) -> dict[str, Any]:
    """Faithfulness result shaped like core.evaluation.ragas.ragas_faithfulness_data's
    output, but scored by the heuristic above, not the real Ragas SDK."""
    score = heuristic_faithfulness_score(draft_plan, evidence)
    pass_fail = score >= FAITHFULNESS_PASS_THRESHOLD
    return {
        "faithfulness_score": score,
        "pass_fail": pass_fail,
        "method": "heuristic_evidence_grounding",
        "threshold": FAITHFULNESS_PASS_THRESHOLD,
        "answer_relevancy_score": None,
        "context_precision_score": None,
        "context_recall_score": None,
        "answer_correctness_score": None,
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


_REPORT_LABELS: tuple[tuple[str, str], ...] = (
    ("citation", "Citation"),
    ("consistency", "Consistency"),
    ("safety", "Safety"),
)


def build_verification_report_for_checks(checks: dict[str, dict[str, Any]]) -> dict[str, Any]:
    passed = True
    feedback_parts: list[str] = []
    for key, label in _REPORT_LABELS:
        check = checks.get(key)
        if check is None:
            continue
        if not check["passed"]:
            passed = False
        if check["issues"]:
            feedback_parts.append(f"{label} issues: {', '.join(check['issues'])}")

    ragas = checks.get("ragas")
    if ragas is not None:
        if not ragas["pass_fail"]:
            passed = False
            feedback_parts.append(
                f"Faithfulness score {ragas['faithfulness_score']} below "
                f"{FAITHFULNESS_PASS_THRESHOLD}"
            )

    return {
        **checks,
        "passed": passed,
        "feedback": "; ".join(feedback_parts) if feedback_parts else None,
    }


def write_verification_artifacts(
    workspace_path: str,
    verification_report: dict[str, Any],
    ragas: dict[str, Any] | None,
) -> None:
    """`ragas` is None for a strategy that never runs the faithfulness check (Phase 5,
    e.g. EXTERNAL_PLAN) -- written as JSON null, an honest record that the check simply
    didn't run for this verification_strategy, not that it ran and failed."""
    vfs = VFS.for_run(Path(workspace_path))
    vfs.write("verify/verification_v1.json", json.dumps(verification_report, indent=2))
    vfs.write("verify/ragas.json", json.dumps(ragas, indent=2))
