"""Fitness capability — graph integration for the swappable executor.

Domain decision logic lives in `core.subgraphs.fitness.executor`; this module
only parses `ExecutionContext`, delegates to the configured executor, and
applies the resulting `CapabilityResult` to orchestration state.
"""

from __future__ import annotations

from core.orchestration.agents.execution_context import parse_execution_context
from core.orchestration.agents.state import OrchestrationState
from core.orchestration.routing.dispatcher import apply_capability_result
from core.subgraphs.fitness.executor import get_fitness_executor
from core.subgraphs.wrapper import merge_subgraph_updates


def invoke_fitness_capability(state: OrchestrationState) -> dict:
    ctx = parse_execution_context(state.get("execution_context"))
    if ctx is None:
        return {"run_complete": True, "final_response": "Missing execution context."}
    result = get_fitness_executor().execute(state, ctx)
    updates = apply_capability_result(state, result)
    if result.artifacts.get("verification_passed") is not None:
        updates["verification_passed"] = result.artifacts["verification_passed"]
    return merge_subgraph_updates(
        state,
        {**updates, "current_node": "fitness"},
        subgraph="fitness",
        steps=["fitness_capability"],
    )
