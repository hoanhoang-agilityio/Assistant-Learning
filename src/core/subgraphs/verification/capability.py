"""Verification capability — graph integration for the swappable executor.

Domain decision logic lives in `core.subgraphs.verification.executor`; this
module only delegates to the configured executor and applies the resulting
`CapabilityResult` to orchestration state.
"""

from __future__ import annotations

from core.agents.execution_context import parse_execution_context
from core.agents.state import OrchestrationState
from core.capabilities.dispatcher import apply_capability_result
from core.subgraphs.verification.executor import get_verification_executor
from core.subgraphs.wrapper import merge_subgraph_updates


def invoke_verification_capability(state: OrchestrationState) -> dict:
    ctx = parse_execution_context(state.get("execution_context"))
    result = get_verification_executor().execute(state, ctx)
    updates = apply_capability_result(state, result)
    updates["verification_passed"] = result.artifacts.get("passed", False)
    faithfulness_score = result.artifacts.get("faithfulness_score")
    if faithfulness_score is not None:
        updates["faithfulness_score"] = faithfulness_score
    checks_run = result.metadata.get("checks_run") or []
    return merge_subgraph_updates(
        state,
        {**updates, "current_node": "verification"},
        subgraph="verification",
        steps=[f"verification:{name}" for name in checks_run],
    )
