"""Golden-case pipeline benchmark: runs planning->research->fitness->verification
end to end and reports the heuristic faithfulness score each case's pipeline run
produced. See core.evaluation.ragas for the real Ragas SDK scorer, which
evaluate_draft_faithfulness below can also invoke for comparison when
settings.verification_use_real_ragas is set."""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from core.config.settings import get_settings
from core.evaluation.ragas import ragas_faithfulness_data
from core.graph.run import create_initial_state
from core.llm.factory import get_standard_llm
from core.mcp.tavily_client import TavilyMCPClient, configure_tavily_client
from core.subgraphs.fitness.graph import build_fitness_subgraph
from core.subgraphs.fitness.planner import configure_fitness_planner
from core.subgraphs.fitness.state import FitnessState
from core.subgraphs.fitness.utils import build_default_structured_workout
from core.subgraphs.planning.utils import seed_execution_plan
from core.subgraphs.research.graph import build_research_subgraph
from core.subgraphs.research.state import ResearchState
from core.subgraphs.verification.graph import build_verification_subgraph
from core.subgraphs.verification.state import VerificationState
from core.subgraphs.verification.utils import (
    FAITHFULNESS_PASS_THRESHOLD,
    heuristic_faithfulness_data,
)


@dataclass(frozen=True)
class GoldenCase:
    """Single golden benchmark case."""

    case_id: str
    query: str
    profile: dict[str, Any]
    constraints: dict[str, Any]
    request_type: str
    min_faithfulness: float


@dataclass(frozen=True)
class BenchmarkResult:
    """Faithfulness result for one golden case.

    faithfulness_score/pass_fail are always the heuristic, pipeline-authoritative
    values (whatever the golden case's actual verification subgraph run
    produced). real_faithfulness_score/real_pass_fail are additive comparison
    data from the real Ragas SDK, populated only when
    settings.verification_use_real_ragas is on -- they never replace the
    heuristic values or change this case's pass/fail verdict.
    """

    case_id: str
    faithfulness_score: float
    pass_fail: bool
    min_faithfulness: float
    workspace_path: str
    real_faithfulness_score: float | None = None
    real_pass_fail: bool | None = None


def load_golden_cases(path: Path) -> list[GoldenCase]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    cases = payload.get("cases", payload)
    return [
        GoldenCase(
            case_id=str(item["id"]),
            query=str(item["query"]),
            profile=dict(item["profile"]),
            constraints=dict(item.get("constraints", {})),
            request_type=str(item.get("request_type", "general_fitness")),
            min_faithfulness=float(item.get("min_faithfulness", FAITHFULNESS_PASS_THRESHOLD)),
        )
        for item in cases
    ]


def _build_mock_tavily_client() -> TavilyMCPClient:
    def search(query: str) -> dict[str, Any]:
        return {
            "results": [
                {
                    "title": f"Evidence for {query}",
                    "url": "https://example.edu/fitness-training",
                    "content": (
                        "hypertrophy training evidence macro targets training plan "
                        "strength programming nutrition"
                    ),
                    "score": 0.92,
                }
            ]
        }

    def extract(urls: list[str]) -> dict[str, Any]:
        return {
            "results": [
                {
                    "url": url,
                    "raw_content": (
                        "hypertrophy training evidence macro targets training plan "
                        "strength programming nutrition evidence summary"
                    ),
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
    """Execute planning → research → fitness → verification for one golden case."""
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
        seed_execution_plan(initial["workspace_path"], case.profile)
        research_state = ResearchState(
            query=case.query,
            request_type=case.request_type,
            workspace_path=initial["workspace_path"],
            profile={},
            execution_plan={},
            evidence=[],
            sources=[],
            structured_findings=None,
            evidence_summary=None,
            blocked_by_todos=False,
            agent_iterations=0,
            is_reresearch=False,
        )
        build_research_subgraph().invoke(research_state)
        fitness_state = FitnessState(
            workspace_path=initial["workspace_path"],
            profile=case.profile,
            constraints=case.constraints,
            execution_plan={},
            structured_findings=None,
            evidence_summary=None,
            verification_feedback=None,
            macro_targets={},
            training_constraints={},
            structured_workout=None,
            safety_result={"passed": False, "feedback": []},
            planner_feedback=[],
            planner_attempts=0,
            max_planner_attempts=get_settings().max_planner_attempts,
            is_verification_rerun=False,
            draft_plan=None,
        )
        build_fitness_subgraph().invoke(fitness_state)
        verification_state = VerificationState(
            workspace_path=initial["workspace_path"],
            draft_plan="",
            sources=[],
            evidence=[],
            macro_targets={},
            training_plan={},
            profile=case.profile,
            constraints=case.constraints,
            safety_flags=[],
            verification_report={},
            feedback=None,
            faithfulness_score=None,
            pass_fail=False,
        )
        verification_result = build_verification_subgraph().invoke(verification_state)
        faithfulness_score = float(verification_result["faithfulness_score"] or 0.0)

        real_faithfulness_score: float | None = None
        real_pass_fail: bool | None = None
        if get_settings().verification_use_real_ragas:
            real_result = evaluate_draft_faithfulness(
                verification_result["draft_plan"],
                verification_result["evidence"],
                query=case.query,
            )
            real_faithfulness_score = real_result["faithfulness_score"]
            real_pass_fail = real_result["pass_fail"]

        return BenchmarkResult(
            case_id=case.case_id,
            faithfulness_score=faithfulness_score,
            pass_fail=faithfulness_score >= case.min_faithfulness,
            min_faithfulness=case.min_faithfulness,
            workspace_path=initial["workspace_path"],
            real_faithfulness_score=real_faithfulness_score,
            real_pass_fail=real_pass_fail,
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
    draft_plan: str, evidence: list[dict[str, Any]], *, query: str = ""
) -> dict[str, Any]:
    """Score a draft plan against evidence.

    Uses the real Ragas SDK (core.evaluation.ragas) when
    settings.verification_use_real_ragas is on, else the same heuristic
    proxy production verification uses. This is the only place in this
    plan's scope that reads verification_use_real_ragas -- production's
    _ragas_faithfulness_node always uses the heuristic regardless.
    """
    if get_settings().verification_use_real_ragas:
        return ragas_faithfulness_data(
            draft_plan, evidence, query=query, judge_llm=get_standard_llm()
        )
    return heuristic_faithfulness_data(draft_plan, evidence)


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
            "planted_issue": case.planted_issue,
            "heuristic_faithfulness_score": heuristic_result["faithfulness_score"],
            "heuristic_pass_fail": heuristic_result["pass_fail"],
        }
        if include_real:
            real_result = ragas_faithfulness_data(
                case.draft_plan, case.evidence, query=case.query, judge_llm=get_standard_llm()
            )
            row["real_faithfulness_score"] = real_result["faithfulness_score"]
            row["real_pass_fail"] = real_result["pass_fail"]
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
