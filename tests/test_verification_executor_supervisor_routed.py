"""Unit test for `SupervisorRoutedVerificationExecutor` -- the AgentResult-only
Verification executor (Phase 2 of the hybrid Supervisor routing migration). Same
4-check policy as `DeterministicVerificationExecutor`, just field-mapped onto
status/summary/artifacts/metadata instead of output/next_request."""

from pathlib import Path
from typing import Any

from core.agents.execution_context import build_execution_context
from core.graph.run import create_initial_state
from core.subgraphs.verification.executor import SupervisorRoutedVerificationExecutor


def test_verification_executor_reports_agent_result_shape(
    workspace_root: Path, complete_profile: dict[str, Any]
) -> None:
    state = create_initial_state(
        run_id="verify-exec-v2",
        thread_id="verify-exec-thread-v2",
        query="Build me a 4-day plan",
        user_profile=complete_profile,
        constraints={"days_per_week": 4, "equipment": "gym"},
        workspace_root=workspace_root,
    )
    ctx = build_execution_context(intent="build_plan")

    result = SupervisorRoutedVerificationExecutor().execute(state, ctx)

    assert result.status == "completed"
    assert result.next_request is None
    assert "passed" in result.artifacts
    assert "faithfulness_score" in result.artifacts
    assert result.metadata["checks_run"] == ["citation", "consistency", "safety", "ragas"]
