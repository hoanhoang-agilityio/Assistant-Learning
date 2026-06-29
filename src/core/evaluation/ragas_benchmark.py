"""Faithfulness benchmark utilities (heuristic grounding proxy until Ragas SDK import is fixed)."""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from core.graph.run import create_initial_state
from core.mcp.tavily_client import TavilyMCPClient, configure_tavily_client
from core.subgraphs.fitness.graph import build_fitness_subgraph
from core.subgraphs.fitness.state import FitnessState
from core.subgraphs.planning.utils import write_planning_todos
from core.subgraphs.research.graph import build_research_subgraph
from core.subgraphs.research.state import ResearchState
from core.subgraphs.verification.graph import build_verification_subgraph
from core.subgraphs.verification.state import VerificationState
from core.subgraphs.verification.utils import FAITHFULNESS_PASS_THRESHOLD, ragas_faithfulness_data


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
    """Faithfulness result for one golden case."""

    case_id: str
    faithfulness_score: float
    pass_fail: bool
    min_faithfulness: float
    workspace_path: str


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
    try:
        write_planning_todos(case.profile, case.request_type, initial["workspace_path"])
        research_state = ResearchState(
            query=case.query,
            request_type=case.request_type,
            workspace_path=initial["workspace_path"],
            todos=[],
            research_questions=[],
            evidence=[],
            sources=[],
            evidence_summary=None,
            blocked_by_todos=False,
        )
        build_research_subgraph().invoke(research_state)
        fitness_state = FitnessState(
            workspace_path=initial["workspace_path"],
            profile=case.profile,
            constraints=case.constraints,
            evidence_summary=None,
            verification_feedback=None,
            macro_targets={},
            training_constraints={},
            training_plan=None,
            draft_plan=None,
            safety_flags=[],
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
        return BenchmarkResult(
            case_id=case.case_id,
            faithfulness_score=faithfulness_score,
            pass_fail=faithfulness_score >= case.min_faithfulness,
            min_faithfulness=case.min_faithfulness,
            workspace_path=initial["workspace_path"],
        )
    finally:
        configure_tavily_client(None)


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


def evaluate_draft_faithfulness(draft_plan: str, evidence: list[dict[str, Any]]) -> dict[str, Any]:
    """Score a draft plan against evidence using the production faithfulness proxy."""
    return ragas_faithfulness_data(draft_plan, evidence)
