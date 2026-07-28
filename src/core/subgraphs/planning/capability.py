"""Planning capability — graph integration for the swappable executor.

Domain decision logic lives in `core.subgraphs.planning.executor`; this
module only parses `ExecutionContext`, delegates to the configured executor,
and applies the resulting `CapabilityResult` to orchestration state.
"""

from __future__ import annotations

from core.agents.execution_context import parse_execution_context
from core.agents.state import OrchestrationState
from core.capabilities.dispatcher import apply_capability_result
from core.subgraphs.planning.executor import PLANNING_OUTPUT_PATH, get_planning_executor
from core.subgraphs.wrapper import merge_subgraph_updates

__all__ = ["PLANNING_OUTPUT_PATH", "invoke_planning_capability"]


def invoke_planning_capability(state: OrchestrationState) -> dict:
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
