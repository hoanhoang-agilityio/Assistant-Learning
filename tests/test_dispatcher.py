"""apply_capability_result is the single place a capability's AgentResult gets
recorded onto orchestration state. `{planning,fitness}_synced_revision` in
particular are load-bearing for the Policy Engine's revision_requested rule (see
core.orchestration.routing.policy_engine) -- each must only be stamped for its own
capability, using the *current* revision_count. (`user_synced_revision` is stamped
separately by core.capabilities.user.graph.invoke_user_subgraph, which doesn't go
through this dispatcher.)"""

from uuid import UUID

import pytest

from core.orchestration.routing.dispatcher import apply_capability_result
from core.shared.execution_context import CapabilityResult

_REQUEST_ID = UUID("12345678-1234-5678-1234-567812345678")


@pytest.mark.parametrize("capability", ["planning", "fitness"])
def test_synced_result_stamps_its_own_synced_revision_from_current_revision_count(
    capability: str,
) -> None:
    state = {"capability_results": {}, "last_capability_result": None, "revision_count": 2}
    result = CapabilityResult(request_id=_REQUEST_ID, capability=capability, status="completed")

    updates = apply_capability_result(state, result)

    assert updates[f"{capability}_synced_revision"] == 2
    assert updates["last_capability_result"]["capability"] == capability


def test_unrelated_result_does_not_touch_any_synced_revision_field() -> None:
    state = {"capability_results": {}, "last_capability_result": None, "revision_count": 2}
    result = CapabilityResult(request_id=_REQUEST_ID, capability="verification", status="completed")

    updates = apply_capability_result(state, result)

    assert "fitness_synced_revision" not in updates
    assert "planning_synced_revision" not in updates
    assert "user_synced_revision" not in updates
