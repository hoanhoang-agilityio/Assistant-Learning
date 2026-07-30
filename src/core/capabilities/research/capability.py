"""Research capability — graph integration for the swappable executor.

Domain decision logic lives in `core.capabilities.research.executor`; this
module only parses `ExecutionContext`, delegates to the configured executor,
and applies the resulting `CapabilityResult` to orchestration state. Research
is standalone-callable (a direct research question) or a returning capability
(an evidence handoff from another capability) either way.
"""

from __future__ import annotations

from core.capabilities.research.executor import get_research_executor
from core.capabilities.wrapper import merge_subgraph_updates
from core.orchestration.routing.dispatcher import apply_capability_result
from core.orchestration.state import OrchestrationState
from core.shared.execution_context import parse_execution_context


def invoke_research_capability(state: OrchestrationState) -> dict:
    ctx = parse_execution_context(state.get("execution_context"))
    result = get_research_executor().execute(state, ctx)
    updates = apply_capability_result(state, result)
    return merge_subgraph_updates(
        state,
        {**updates, "current_node": "research"},
        subgraph="research",
        steps=["research_agent", "write_artifacts"],
    )
