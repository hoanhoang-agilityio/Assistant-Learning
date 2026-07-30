import json
import logging
import re
from pathlib import Path
from typing import Any

from core.config.settings import get_settings
from core.llm.serializers import compact_evidence_for_llm
from core.subgraphs.fitness.utils import build_workout_summary
from core.vfs import VFS

logger = logging.getLogger(__name__)

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

    Callers should pass grounded_claims text (not the full final_plan) so
    engine-authored macros/training sections are not scored as research claims.
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
        for marker in (
            "macro targets",
            "training plan",
            "evidence summary",
            "evidence applied",
            "grounded claims",
            "source:",
        )
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


def evaluate_faithfulness(
    draft_plan: str,
    evidence: list[dict[str, Any]],
    *,
    query: str = "",
    reference: str | None = None,
    use_real: bool,
) -> dict[str, Any]:
    """Single dispatch point for faithfulness scoring -- heuristic or real Ragas SDK,
    chosen by the explicit `use_real` the caller passes in (this function never reads
    settings itself; production and the benchmark each decide their own gating).

    Callers: verification/executor.py (production, gated behind
    settings.verification_production_use_real_ragas, off by default) and
    core/evaluation/ragas_benchmark.py (benchmark, passes
    settings.verification_use_real_ragas). Having one function means the two
    call sites can no longer silently drift into different dispatch logic over time
    (2026-07-30 Phase 1 remediation -- see docs/reports/known_limitations_remediation_plan.md, L1).

    When use_real is True, heuristic_faithfulness_data is the fallback on ANY
    failure in the real path -- rate limit already exceeded, the OpenAI call
    itself failing, or a Ragas SDK error (2026-07-30 Phase 3: "heuristic becomes
    the fallback", not a second gate to configure). A live user-facing request
    must never fail outright because the real judge call hit a transient
    problem; degrading to the free heuristic for that one call is safer than
    blocking plan delivery.
    """
    if use_real:
        try:
            return _evaluate_faithfulness_real(
                draft_plan, evidence, query=query, reference=reference
            )
        except Exception:
            logger.exception(
                "Real Ragas faithfulness scoring failed; falling back to the "
                "heuristic proxy for this call."
            )
    return heuristic_faithfulness_data(draft_plan, evidence)


def _evaluate_faithfulness_real(
    draft_plan: str,
    evidence: list[dict[str, Any]],
    *,
    query: str,
    reference: str | None,
) -> dict[str, Any]:
    """The use_real=True path, split out so evaluate_faithfulness's try/except
    covers every failure mode uniformly (rate limit, API error, SDK error).

    The `ragas` SDK import graph is heavy (pulls in `datasets`/pandas/its own
    LLM-wrapper stack) -- deferred here (not a module-level import) so
    importing this module, or calling evaluate_faithfulness with
    use_real=False, never pays that cost.

    Real Ragas calls the judge LLM through its own internal harness, not this
    repo's core.llm.factory wrappers -- so unlike every other LLM call in this
    codebase, it would otherwise be invisible to the per-user rate limiter and
    to token_cost.md. get_openai_callback() captures the real token usage so
    it can be checked/recorded through the same AIRateLimiter every other call
    goes through (get_rate_limit_user_id() is the same context var
    record_active_user_response() reads elsewhere in this codebase).
    """
    from langchain_community.callbacks import get_openai_callback

    from core.evaluation.ragas import ragas_faithfulness_data
    from core.llm.factory import get_rate_limiter, get_standard_llm
    from core.rate_limit.context import get_rate_limit_user_id

    settings = get_settings()
    rate_limiter = get_rate_limiter()
    user_id = get_rate_limit_user_id()
    rate_limiter.check_active_user_tokens()

    with get_openai_callback() as callback:
        result = ragas_faithfulness_data(
            draft_plan,
            evidence,
            query=query,
            judge_llm=get_standard_llm(),
            reference=reference,
        )
    rate_limiter.record_usage(
        user_id,
        input_tokens=callback.prompt_tokens,
        output_tokens=callback.completion_tokens,
        model_name=settings.openai_standard_model,
    )
    return result


_REPORT_LABELS: tuple[tuple[str, str], ...] = (
    ("citation", "Citation"),
    ("consistency", "Consistency"),
    ("safety", "Safety"),
)

# Which capability owns fixing a failing check -- research owns evidence/
# citations, fitness owns the macro/workout numbers it computed itself.
# "ragas" (faithfulness) is a research-owned failure: a low score means the
# draft's claims aren't actually supported by the evidence research gathered,
# which fitness has no way to fix by regenerating a workout.
_CHECK_OWNERS: dict[str, str] = {
    "citation": "research",
    "ragas": "research",
    "consistency": "fitness",
    "safety": "fitness",
}

# When multiple owners are implicated by different failing checks in the same
# report, research is retried first: fitness's macro/workout numbers assume
# research's evidence and citations are already correct, so a research-owned
# fix may also resolve a downstream fitness-owned symptom, but never the
# reverse. See docs/reports/known_limitations_remediation_plan.md, L1, Phase 4.
_OWNER_RETRY_PRECEDENCE: tuple[str, ...] = ("research", "fitness")


def _determine_retry_target(checks: dict[str, dict[str, Any]]) -> str | None:
    """Which capability should be retried automatically, given which checks
    failed -- None when everything passed, or no failing check has a known
    owner (nothing to usefully retry)."""
    failing_owners: set[str] = set()
    for key, owner in _CHECK_OWNERS.items():
        check = checks.get(key)
        if check is None:
            continue
        check_passed = check["pass_fail"] if key == "ragas" else check["passed"]
        if not check_passed:
            failing_owners.add(owner)
    for owner in _OWNER_RETRY_PRECEDENCE:
        if owner in failing_owners:
            return owner
    return None


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
        "retry_target": _determine_retry_target(checks) if not passed else None,
    }


def write_verification_artifacts(
    workspace_path: str,
    verification_report: dict[str, Any],
    ragas: dict[str, Any] | None,
) -> None:
    """`ragas` is None when the requesting capability didn't include "faithfulness" in
    its requested checks -- written as JSON null, an honest record that the check simply
    didn't run, not that it ran and failed."""
    vfs = VFS.for_run(Path(workspace_path))
    vfs.write("verify/verification_v1.json", json.dumps(verification_report, indent=2))
    vfs.write("verify/ragas.json", json.dumps(ragas, indent=2))
