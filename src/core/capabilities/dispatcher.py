"""Records a capability's AgentResult onto orchestration state.

No longer a routing module -- the Supervisor (`core.agents.supervisor`) is the
single routing authority now, informed by the deterministic Policy Engine
(`core.capabilities.policy_engine`). This module only applies a capability's own
reported result to state; it never decides what runs next.

`CapabilityRequest`/`make_capability_request` are kept only because the legacy
`Deterministic*Executor` classes (kept for their existing direct unit tests, no
longer reachable from the compiled graph) still construct them -- nothing in the
live graph consumes `next_request` anymore.
"""

from __future__ import annotations

from typing import Any
from uuid import uuid4

from core.agents.execution_context import CapabilityRequest, CapabilityResult
from core.agents.state import OrchestrationState


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


def make_capability_request(
    *,
    capability: str,
    reason: str,
    return_to: str | None = None,
    payload: dict[str, Any] | None = None,
) -> CapabilityRequest:
    return CapabilityRequest(
        request_id=uuid4(),
        capability=capability,  # type: ignore[arg-type]
        reason=reason,
        payload=payload or {},
        return_to=return_to,  # type: ignore[arg-type]
    )
