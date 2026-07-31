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
    update: dict[str, Any] = {
        "capability_results": results,
        "last_capability_result": result.model_dump(mode="json"),
    }
    if result.capability in ("planning", "fitness"):
        # Records which revision cycle this capability just reprocessed for -- see
        # `OrchestrationState.{planning,fitness}_synced_revision` and the Policy
        # Engine's revision_requested rule, which compares these against
        # `revision_count` to sequence User -> Planning -> Fitness through a
        # revision instead of re-running all three on every hop. (User doesn't
        # go through this dispatcher -- see invoke_user_subgraph, which stamps
        # `user_synced_revision` itself.)
        update[f"{result.capability}_synced_revision"] = int(state.get("revision_count") or 0)
    return update
