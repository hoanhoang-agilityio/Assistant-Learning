"""Unit test for `SupervisorRoutedResearchExecutor` -- the AgentResult-only Research
executor (Phase 2 of the hybrid Supervisor routing migration). Research never
decided its own next hop even in the old design, so this is a field-mapping-only
change; `research_agent_override` (conftest autouse) stubs `run_research_agent`."""

from pathlib import Path
from typing import Any

from core.capabilities.research.executor import SupervisorRoutedResearchExecutor
from core.orchestration.graph.run import create_initial_state
from core.shared.execution_context import build_execution_context


def test_research_question_reports_summary_only(
    workspace_root: Path, complete_profile: dict[str, Any]
) -> None:
    state = create_initial_state(
        run_id="research-q-v2",
        thread_id="research-q-thread-v2",
        query="What does research say about HIIT for fat loss?",
        user_profile=complete_profile,
        constraints={"days_per_week": 4, "equipment": "gym"},
        workspace_root=workspace_root,
    )
    ctx = build_execution_context(intent="research_question")

    result = SupervisorRoutedResearchExecutor().execute(state, ctx)

    assert result.status == "completed"
    assert result.next_request is None
    assert result.summary
    assert result.artifacts == {}


def test_research_for_plan_generation_reports_structured_findings(
    workspace_root: Path, complete_profile: dict[str, Any]
) -> None:
    state = create_initial_state(
        run_id="research-plan-v2",
        thread_id="research-plan-thread-v2",
        query="Build me a 4-day plan",
        user_profile=complete_profile,
        constraints={"days_per_week": 4, "equipment": "gym"},
        workspace_root=workspace_root,
    )
    ctx = build_execution_context(intent="build_plan")

    result = SupervisorRoutedResearchExecutor().execute(state, ctx)

    assert result.status == "completed"
    assert result.next_request is None
    assert "structured_findings" in result.artifacts
    assert "evidence_summary" in result.artifacts
