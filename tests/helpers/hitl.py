import json
from pathlib import Path
from typing import Any
from uuid import uuid4

from langgraph.graph.state import CompiledStateGraph

from core.adapters.vfs import VFS
from core.orchestration.agents.execution_context import CapabilityResult, build_execution_context
from core.orchestration.graph.run import create_initial_state


def pause_before_hitl(
    graph: CompiledStateGraph,
    run_id: str,
    tmp_path: Path,
    *,
    verification_passed: bool = True,
    faithfulness_score: float = 0.95,
    overrides: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Inject a checkpoint as if Verification had just completed, then let the
    Supervisor route to HITL.

    Mirrors the real Fitness -> Verification -> HITL sequence (see
    `core.orchestration.routing.policy_engine`'s `_hitl_outcome`/`artifact_requires_verification`
    rules) without running the full planning/research/fitness/verification
    pipeline, so HITL resume tests can exercise `interrupt_before=["hitl"]` and the
    Supervisor's routing decision directly.
    """
    config = {"configurable": {"thread_id": run_id}}
    initial = create_initial_state(
        run_id=run_id,
        thread_id=run_id,
        query="Approve my plan",
        workspace_root=tmp_path / run_id,
    )
    vfs = VFS.for_run(Path(initial["workspace_path"]))
    vfs.write("fitness/final_plan.md", "# Final Plan\n\nMacro targets and training days.")
    vfs.write(
        "verify/verification_v1.json", json.dumps({"passed": verification_passed, "feedback": None})
    )

    verification_result = CapabilityResult(
        request_id=uuid4(),
        capability="verification",
        status="completed",
        summary="Verification complete.",
        artifacts={"passed": verification_passed, "faithfulness_score": faithfulness_score},
    )
    ctx = build_execution_context(intent="build_plan")
    state = {
        **initial,
        "execution_context": ctx.model_dump(mode="json"),
        "intent": "build_plan",
        "profile_complete": True,
        "profile_valid": True,
        "verification_passed": verification_passed,
        "faithfulness_score": faithfulness_score,
        "last_capability_result": verification_result.model_dump(mode="json"),
        "current_node": "verification",
        **(overrides or {}),
    }
    graph.update_state(config, state, as_node="verification")
    # `as_node="verification"` only computes verification's own (unconditional)
    # outgoing edge to "supervisor" -- one more step is needed to actually run the
    # Supervisor node (Router Judge -> Policy Engine) and pause at the
    # `interrupt_before=["hitl"]` boundary.
    graph.invoke(None, config)
    return config


def run_to_hitl_pause(
    graph: CompiledStateGraph,
    run_id: str,
    tmp_path: Path,
    *,
    query: str,
    user_profile: dict[str, Any],
    constraints: dict[str, Any],
) -> dict[str, Any]:
    """Drive a real build_plan run (via the stubbed planning/fitness/research
    agents configured in conftest) through to the HITL pause, so resume tests
    that need Fitness to actually re-execute (e.g. a revision) have consistent
    upstream VFS state (research findings, planning output) to read back."""
    config = {"configurable": {"thread_id": run_id}}
    state = create_initial_state(
        run_id=run_id,
        thread_id=run_id,
        query=query,
        user_profile=user_profile,
        constraints=constraints,
        workspace_root=tmp_path / run_id,
    )
    graph.invoke(state, config)
    return config
