"""Unit test for `SupervisorRoutedPlanningExecutor` -- the AgentResult-only Planning
executor (Phase 2 of the hybrid Supervisor routing migration)."""

from pathlib import Path
from typing import Any

from core.agents.execution_context import build_execution_context
from core.graph.run import create_initial_state
from core.planning.executor import PLANNING_OUTPUT_PATH, SupervisorRoutedPlanningExecutor


def test_planning_executor_reports_completed_with_no_next_request(
    workspace_root: Path, complete_profile: dict[str, Any]
) -> None:
    state = create_initial_state(
        run_id="plan-run-v2",
        thread_id="plan-thread-v2",
        query="Build me a 4-day plan",
        user_profile=complete_profile,
        constraints={"days_per_week": 4, "equipment": "gym"},
        workspace_root=workspace_root,
    )
    ctx = build_execution_context(intent="build_plan")

    result = SupervisorRoutedPlanningExecutor().execute(state, ctx)

    assert result.status == "completed"
    assert result.next_request is None
    assert result.artifacts["planning_output_path"] == PLANNING_OUTPUT_PATH
