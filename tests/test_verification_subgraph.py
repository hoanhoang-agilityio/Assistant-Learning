import json
from pathlib import Path
from typing import Any

import pytest

from core.agents.state import OrchestrationState
from core.graph.run import create_initial_state
from core.subgraphs.fitness.graph import build_fitness_subgraph
from core.subgraphs.fitness.state import FitnessState
from core.subgraphs.verification.agent import VerificationAgent
from core.subgraphs.verification.graph import (
    build_verification_subgraph,
    invoke_verification_subgraph,
)
from core.subgraphs.verification.state import VerificationState
from core.subgraphs.verification.tools import (
    citation_check,
    consistency_check,
    ragas_faithfulness,
    safety_check,
)
from core.subgraphs.verification.utils import FAITHFULNESS_PASS_THRESHOLD
from core.vfs import VFS
from tests.helpers.planning import seed_execution_plan


@pytest.fixture
def workspace_root(tmp_path: Path) -> Path:
    return tmp_path / "workspace"


@pytest.fixture
def complete_profile() -> dict[str, Any]:
    return {
        "age": 30,
        "sex": "male",
        "height_cm": 175,
        "current_weight_kg": 85.0,
        "target_weight_kg": 75.0,
        "activity_level": "gym_3x_week",
        "goal": "fat_loss",
    }


@pytest.fixture
def verification_state(
    workspace_root: Path,
    complete_profile: dict[str, Any],
) -> VerificationState:
    initial = create_initial_state(
        run_id="verify-run",
        thread_id="verify-thread",
        query="I want to lose weight with strength training.",
        user_profile=complete_profile,
        workspace_root=workspace_root,
    )
    seed_execution_plan(initial["workspace_path"], complete_profile)
    vfs = VFS.for_run(Path(initial["workspace_path"]))
    evidence = [
        {
            "document_id": "doc_0",
            "url": "https://example.edu/fitness-training",
            "content": "hypertrophy training evidence for strength programming",
            "provider": "tavily",
        }
    ]
    vfs.write(
        "research/sources.json",
        json.dumps(
            [
                {
                    "source_id": "src_0",
                    "title": "Hypertrophy training evidence",
                    "url": "https://example.edu/fitness-training",
                    "snippet": "hypertrophy training evidence",
                    "score": 0.92,
                    "provider": "tavily",
                }
            ]
        ),
    )
    vfs.write(
        "research/findings.json",
        json.dumps(
            {
                "evidence": evidence,
                "evidence_summary": "hypertrophy training evidence collected",
                "source_count": 1,
            }
        ),
    )

    fitness_state = FitnessState(
        workspace_path=initial["workspace_path"],
        profile=complete_profile,
        constraints={"days_per_week": 3, "equipment": "gym"},
        execution_plan={},
        structured_findings=None,
        evidence_summary="hypertrophy training evidence collected",
        verification_feedback=None,
        macro_targets={},
        training_constraints={},
        structured_workout=None,
        safety_result={"passed": False, "feedback": []},
        planner_feedback=[],
        planner_attempts=0,
        draft_plan=None,
    )
    build_fitness_subgraph().invoke(fitness_state)

    return VerificationState(
        workspace_path=initial["workspace_path"],
        draft_plan="",
        sources=[],
        evidence=[],
        macro_targets={},
        training_plan={},
        profile=complete_profile,
        constraints={"days_per_week": 3},
        safety_flags=[],
        verification_report={},
        feedback=None,
        faithfulness_score=None,
        pass_fail=False,
    )


def test_citation_check_passes_with_evidence_section(verification_state: VerificationState) -> None:
    vfs = VFS.for_run(Path(verification_state["workspace_path"]))
    draft_plan = vfs.read("fitness/final_plan.md")
    sources = json.loads(vfs.read("research/sources.json"))
    result = citation_check.invoke({"draft_plan": draft_plan, "sources": sources})
    assert result["passed"] is True


def test_consistency_check_validates_macro_and_day_count(
    verification_state: VerificationState,
) -> None:
    vfs = VFS.for_run(Path(verification_state["workspace_path"]))
    draft_plan = vfs.read("fitness/final_plan.md")
    calculations = json.loads(vfs.read("fitness/calculations.json"))
    result = consistency_check.invoke(
        {
            "draft_plan": draft_plan,
            "macro_targets": calculations["macro_targets"],
            "training_plan": calculations["training_plan_summary"],
        }
    )
    assert result["passed"] is True


def test_safety_check_fails_on_critical_flags() -> None:
    result = safety_check.invoke(
        {
            "draft_plan": "Plan draft",
            "profile": {},
            "constraints": {},
            "safety_flags": ["calories_below_safe_minimum"],
        }
    )
    assert result["passed"] is False
    assert "calories_below_safe_minimum" in result["issues"]


def test_ragas_faithfulness_meets_threshold(verification_state: VerificationState) -> None:
    vfs = VFS.for_run(Path(verification_state["workspace_path"]))
    draft_plan = vfs.read("fitness/final_plan.md")
    findings = json.loads(vfs.read("research/findings.json"))
    result = ragas_faithfulness.invoke(
        {
            "draft_plan": draft_plan,
            "evidence": findings["evidence"],
        }
    )
    assert result["faithfulness_score"] >= FAITHFULNESS_PASS_THRESHOLD
    assert result["pass_fail"] is True


def test_verification_subgraph_writes_vfs_artifacts(verification_state: VerificationState) -> None:
    graph = build_verification_subgraph()
    result = graph.invoke(verification_state)
    vfs = VFS.for_run(Path(verification_state["workspace_path"]))
    assert vfs.exists("verify/verification_v1.json")
    assert vfs.exists("verify/ragas.json")
    report = json.loads(vfs.read("verify/verification_v1.json"))
    ragas = json.loads(vfs.read("verify/ragas.json"))
    assert report["passed"] is True
    assert result["pass_fail"] is True
    assert ragas["faithfulness_score"] >= FAITHFULNESS_PASS_THRESHOLD


def test_verification_agent_returns_structured_report(
    verification_state: VerificationState,
) -> None:
    orchestration_state: OrchestrationState = {
        "run_id": "verify-run",
        "thread_id": "verify-thread",
        "current_node": "fitness",
        "query": "lose weight",
        "user_profile": verification_state["profile"],
        "constraints": verification_state["constraints"],
        "request_type": "fat_loss",
        "affected_domains": ["planning", "research", "fitness", "verify"],
        "route_decision": None,
        "retry_count": 0,
        "replan_count": 0,
        "verification_passed": False,
        "faithfulness_score": None,
        "waiting_for_user": False,
        "approval_status": None,
        "user_response": None,
        "workspace_path": verification_state["workspace_path"],
        "final_artifact_path": None,
    }
    updates = VerificationAgent().run(orchestration_state)
    assert updates["current_node"] == "verification"
    assert updates["verification_passed"] is True
    assert updates["faithfulness_score"] >= FAITHFULNESS_PASS_THRESHOLD


def test_invoke_verification_subgraph_marks_failure_without_draft(workspace_root: Path) -> None:
    initial = create_initial_state(
        run_id="verify-fail",
        thread_id="verify-fail-thread",
        query="test",
        workspace_root=workspace_root,
    )
    orchestration_state: OrchestrationState = {
        **initial,
        "request_type": "fat_loss",
        "affected_domains": ["planning", "research", "fitness", "verify"],
    }
    updates = invoke_verification_subgraph(orchestration_state)
    assert updates["verification_passed"] is False
    assert updates["faithfulness_score"] is not None
