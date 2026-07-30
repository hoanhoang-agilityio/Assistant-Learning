"""Records a capability's AgentResult onto orchestration state.

No longer a routing module -- the Supervisor (`core.orchestration.agents.supervisor`) is the
single routing authority now, informed by the deterministic Policy Engine
(`core.orchestration.routing.policy_engine`). This module only applies a capability's own
reported result to state; it never decides what runs next.
"""

from __future__ import annotations

from typing import Any

from core.orchestration.state import OrchestrationState
from core.shared.execution_context import CapabilityResult


def apply_capability_result(
    state: OrchestrationState,
    result: CapabilityResult,
) -> dict[str, Any]:
    """Record a capability's AgentResult. Never decides what runs next -- the
    Supervisor + Policy Engine read `last_capability_result` on the next hop."""
    results = dict(state.get("capability_results") or {})
    results[str(result.request_id)] = result.model_dump(mode="json")
    return {
        "capability_results": results,
        "last_capability_result": result.model_dump(mode="json"),
    }
