"""Golden-case pipeline benchmark: runs the Research -> Fitness -> Verification
capability chain end to end (bypassing Supervisor's LLM intent classification
for deterministic, fixed-input golden cases) and reports the heuristic
faithfulness score each case's run produced. See core.evaluation.ragas for the
real Ragas SDK scorer, which evaluate_draft_faithfulness below can also invoke
for comparison when settings.verification_use_real_ragas is set."""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from core.agents.execution_context import build_execution_context
from core.config.settings import get_settings
from core.graph.run import create_initial_state
from core.mcp.tavily_client import TavilyMCPClient, configure_tavily_client
from core.subgraphs.fitness.capability import invoke_fitness_capability
from core.subgraphs.fitness.planner import configure_fitness_planner
from core.subgraphs.fitness.utils import build_default_structured_workout
from core.subgraphs.research.capability import invoke_research_capability
from core.subgraphs.verification.capability import invoke_verification_capability
from core.subgraphs.verification.utils import (
    FAITHFULNESS_PASS_THRESHOLD,
    evaluate_faithfulness,
    heuristic_faithfulness_data,
    load_verification_context,
)


@dataclass(frozen=True)
class GoldenCase:
    """Single golden benchmark case."""

    case_id: str
    query: str
    profile: dict[str, Any]
    constraints: dict[str, Any]
    min_faithfulness: float
    reference: str | None = None


@dataclass(frozen=True)
class BenchmarkResult:
    """Faithfulness result for one golden case.

    faithfulness_score/pass_fail are always the heuristic, pipeline-authoritative
    values (whatever the golden case's actual verification capability run
    produced). real_faithfulness_score/real_pass_fail and the other real_*_score
    fields are additive comparison data from the real Ragas SDK, populated only
    when settings.verification_use_real_ragas is on -- they never replace the
    heuristic values or change this case's pass/fail verdict. context_recall and
    answer_correctness are only populated when the golden case has a
    `reference` (ground-truth answer); otherwise they stay None.
    """

    case_id: str
    faithfulness_score: float
    pass_fail: bool
    min_faithfulness: float
    workspace_path: str
    real_faithfulness_score: float | None = None
    real_pass_fail: bool | None = None
    real_answer_relevancy_score: float | None = None
    real_context_precision_score: float | None = None
    real_context_recall_score: float | None = None
    real_answer_correctness_score: float | None = None


def load_golden_cases(path: Path) -> list[GoldenCase]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    cases = payload.get("cases", payload)
    return [
        GoldenCase(
            case_id=str(item["id"]),
            query=str(item["query"]),
            profile=dict(item["profile"]),
            constraints=dict(item.get("constraints", {})),
            min_faithfulness=float(item.get("min_faithfulness", FAITHFULNESS_PASS_THRESHOLD)),
            reference=(str(item["reference"]) if item.get("reference") else None),
        )
        for item in cases
    ]


def _build_mock_tavily_client() -> TavilyMCPClient:
    # Concrete, citable claims rather than keyword-salad filler -- the
    # synthesis prompt now explicitly instructs the LLM to omit a claim
    # rather than fabricate one when evidence doesn't support anything
    # specific (see research/prompts.py SYNTHESIS_SYSTEM_PROMPT), so vague
    # filler content reliably produced an empty (and, pre-2026-07-30,
    # schema-rejected) key_findings list instead of exercising real citation.
    _MOCK_EVIDENCE_CONTENT = (
        "Position-stand guidance for hypertrophy recommends training each "
        "muscle group at least twice per week with loads of 65-85% of "
        "one-rep max for 3-5 sets of 6-12 reps, and consuming 1.6-2.2g of "
        "protein per kg of bodyweight per day. For fat loss, a moderate "
        "deficit of roughly 500 kcal/day preserves lean mass better than "
        "an aggressive deficit."
    )

    def search(query: str, include_domains: list[str] | None = None) -> dict[str, Any]:
        return {
            "results": [
                {
                    "title": f"Evidence for {query}",
                    "url": "https://example.edu/fitness-training",
                    "content": _MOCK_EVIDENCE_CONTENT,
                    "score": 0.92,
                }
            ]
        }

    def extract(urls: list[str]) -> dict[str, Any]:
        return {
            "results": [
                {
                    "url": url,
                    "raw_content": _MOCK_EVIDENCE_CONTENT,
                }
                for url in urls
            ]
        }

    return TavilyMCPClient(search=search, extract=extract)


def run_golden_case(
    case: GoldenCase,
    *,
    workspace_root: Path,
    run_id: str | None = None,
) -> BenchmarkResult:
    """Execute Research -> Fitness -> Verification for one golden case.

    Seeds `execution_context` directly (intent="build_plan") rather than
    going through Supervisor's LLM intent classification, so golden cases
    stay deterministic and free of classification cost/variance.
    """
    resolved_run_id = run_id or f"ragas-{case.case_id}"
    initial = create_initial_state(
        run_id=resolved_run_id,
        thread_id=f"{resolved_run_id}-thread",
        query=case.query,
        user_profile=case.profile,
        constraints=case.constraints,
        workspace_root=workspace_root,
    )
    configure_tavily_client(_build_mock_tavily_client())
    configure_fitness_planner(
        lambda **kwargs: build_default_structured_workout(
            profile=kwargs.get("profile"),
            constraints=kwargs.get("constraints"),
        )
    )
    try:
        ctx = build_execution_context(intent="build_plan")
        state: dict[str, Any] = {**initial, "execution_context": ctx.model_dump(mode="json")}

        state = {**state, **invoke_research_capability(state)}
        state = {**state, **invoke_fitness_capability(state)}
        last_result = state.get("last_capability_result") or {}
        assert (last_result.get("artifacts") or {}).get("artifact_ready"), (
            f"expected Fitness to produce an artifact ready for Verification, got {last_result}"
        )
        state = {**state, **invoke_verification_capability(state)}

        faithfulness_score = float(state.get("faithfulness_score") or 0.0)
        context = load_verification_context(initial["workspace_path"])

        real_faithfulness_score: float | None = None
        real_pass_fail: bool | None = None
        real_answer_relevancy_score: float | None = None
        real_context_precision_score: float | None = None
        real_context_recall_score: float | None = None
        real_answer_correctness_score: float | None = None
        if get_settings().verification_use_real_ragas:
            real_result = evaluate_draft_faithfulness(
                context.get("grounded_claims") or context["draft_plan"],
                context["evidence"],
                query=case.query,
                reference=case.reference,
            )
            real_faithfulness_score = real_result["faithfulness_score"]
            real_pass_fail = real_result["pass_fail"]
            real_answer_relevancy_score = real_result.get("answer_relevancy_score")
            real_context_precision_score = real_result.get("context_precision_score")
            real_context_recall_score = real_result.get("context_recall_score")
            real_answer_correctness_score = real_result.get("answer_correctness_score")

        return BenchmarkResult(
            case_id=case.case_id,
            faithfulness_score=faithfulness_score,
            pass_fail=faithfulness_score >= case.min_faithfulness,
            min_faithfulness=case.min_faithfulness,
            workspace_path=initial["workspace_path"],
            real_faithfulness_score=real_faithfulness_score,
            real_pass_fail=real_pass_fail,
            real_answer_relevancy_score=real_answer_relevancy_score,
            real_context_precision_score=real_context_precision_score,
            real_context_recall_score=real_context_recall_score,
            real_answer_correctness_score=real_answer_correctness_score,
        )
    finally:
        configure_tavily_client(None)
        configure_fitness_planner(None)


def summarize_results(results: list[BenchmarkResult]) -> dict[str, Any]:
    scores = [result.faithfulness_score for result in results]
    passed = sum(1 for result in results if result.pass_fail)
    return {
        "case_count": len(results),
        "passed_count": passed,
        "failed_count": len(results) - passed,
        "pass_rate": round(passed / len(results), 4) if results else 0.0,
        "mean_faithfulness": round(sum(scores) / len(scores), 4) if scores else 0.0,
        "min_faithfulness_threshold": FAITHFULNESS_PASS_THRESHOLD,
        "method": "heuristic_evidence_grounding",
    }


def evaluate_draft_faithfulness(
    draft_plan: str,
    evidence: list[dict[str, Any]],
    *,
    query: str = "",
    reference: str | None = None,
) -> dict[str, Any]:
    """Score a draft plan against evidence.

    Uses the real Ragas SDK (core.evaluation.ragas) when
    settings.verification_use_real_ragas is on, else the same heuristic
    proxy production verification uses -- both paths now go through
    verification.utils.evaluate_faithfulness, the single dispatch point
    production's executor.py also calls (2026-07-30 Phase 1 unification),
    so this and production can no longer silently drift onto different
    dispatch logic. Production's own use_real is hardcoded False regardless
    of this setting -- see executor.py's _PRODUCTION_USE_REAL_RAGAS.

    ``reference`` (ground-truth answer) enables context_recall and
    answer_correctness on the real-SDK path; ignored by the heuristic.
    """
    return evaluate_faithfulness(
        draft_plan,
        evidence,
        query=query,
        reference=reference,
        use_real=get_settings().verification_use_real_ragas,
    )


@dataclass(frozen=True)
class AdversarialCase:
    """A hand-authored (query, evidence, draft_plan) triple with a planted,
    evidence-contradicting or fabricated claim -- unlike GoldenCase, the
    draft_plan is given directly rather than produced by running the
    pipeline, so these exercise the faithfulness scorers in isolation."""

    case_id: str
    query: str
    evidence: list[dict[str, Any]]
    draft_plan: str
    planted_issue: str
    category: str = "uncategorized"


def load_adversarial_cases(path: Path) -> list[AdversarialCase]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    cases = payload.get("cases", payload)
    return [
        AdversarialCase(
            case_id=str(item["id"]),
            query=str(item["query"]),
            evidence=list(item["evidence"]),
            draft_plan=str(item["draft_plan"]),
            planted_issue=str(item.get("planted_issue", "")),
            category=str(item.get("category", "uncategorized")),
        )
        for item in cases
    ]


def compare_faithfulness_scorers(
    cases: list[AdversarialCase], *, include_real: bool
) -> dict[str, Any]:
    """Score each case with the heuristic (and, if include_real, the real Ragas
    SDK) and report the measurable "correlates reasonably" bar from
    known_limitations_remediation_plan.md's L1 step 4:

    - agreement_rate: fraction of cases where heuristic pass_fail ==
      real pass_fail (only meaningful when include_real=True).
    - false_negative_rate: fraction of cases where the heuristic says pass
      but real Ragas says fail -- the heuristic rubber-stamping an
      unfaithful plan, the risk this whole comparison exists to catch.
    """
    per_case: list[dict[str, Any]] = []
    for case in cases:
        heuristic_result = heuristic_faithfulness_data(case.draft_plan, case.evidence)
        row: dict[str, Any] = {
            "case_id": case.case_id,
            "category": case.category,
            "planted_issue": case.planted_issue,
            "heuristic_faithfulness_score": heuristic_result["faithfulness_score"],
            "heuristic_pass_fail": heuristic_result["pass_fail"],
        }
        if include_real:
            real_result = evaluate_faithfulness(
                case.draft_plan, case.evidence, query=case.query, use_real=True
            )
            row["real_faithfulness_score"] = real_result["faithfulness_score"]
            row["real_pass_fail"] = real_result["pass_fail"]
            row["real_answer_relevancy_score"] = real_result.get("answer_relevancy_score")
            row["real_context_precision_score"] = real_result.get("context_precision_score")
            row["real_context_recall_score"] = real_result.get("context_recall_score")
            row["real_answer_correctness_score"] = real_result.get("answer_correctness_score")
            row["agree"] = heuristic_result["pass_fail"] == real_result["pass_fail"]
            row["false_negative"] = heuristic_result["pass_fail"] and not real_result["pass_fail"]
        per_case.append(row)

    summary: dict[str, Any] = {
        "case_count": len(per_case),
        "heuristic_pass_count": sum(1 for row in per_case if row["heuristic_pass_fail"]),
    }
    if include_real and per_case:
        summary["agreement_rate"] = round(
            sum(1 for row in per_case if row["agree"]) / len(per_case), 4
        )
        summary["false_negative_rate"] = round(
            sum(1 for row in per_case if row["false_negative"]) / len(per_case), 4
        )
    return {"summary": summary, "cases": per_case}
