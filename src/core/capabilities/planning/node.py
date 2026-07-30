"""Planning graph node — goal specification only.

Domain decision logic lives in `core.capabilities.planning.executor`; this module parses
`ExecutionContext`, delegates to the configured executor, and applies the
resulting `CapabilityResult` to orchestration state.
"""

from __future__ import annotations

from core.capabilities.planning.executor import PLANNING_OUTPUT_PATH, get_planning_executor
from core.capabilities.wrapper import merge_subgraph_updates
from core.orchestration.agents.execution_context import parse_execution_context
from core.orchestration.agents.state import OrchestrationState
from core.orchestration.routing.dispatcher import apply_capability_result

__all__ = ["PLANNING_OUTPUT_PATH", "invoke_planning_node"]


def invoke_planning_node(state: OrchestrationState) -> dict:
    """Run deterministic goal specification and return orchestration updates."""
    ctx = parse_execution_context(state.get("execution_context"))
    if ctx is None:
        return {"run_complete": True, "final_response": "Missing execution context."}
    result = get_planning_executor().execute(state, ctx)
    updates = apply_capability_result(state, result)
    return merge_subgraph_updates(
        state,
        {**updates, "current_node": "planning"},
        subgraph="planning",
        steps=["build_planning_output"],
    )
