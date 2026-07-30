"""L1 Phase 4: run_supervisor_routing_decision increments verification_retry_count
exactly when the Policy Engine actually auto-retries -- not on every hop, and not
for any other override reason. The Router Judge is stubbed via the autouse
`reset_supervisor_routing_judge` fixture (tests/conftest.py), same as every other
test in this suite -- its proposal doesn't matter here since the deterministic
retry rule always overrides it when the conditions are met."""

from pathlib import Path

from core.adapters.vfs.bootstrap import init_run_workspace
from core.orchestration.agents.supervisor_routing import run_supervisor_routing_decision
from core.orchestration.state import OrchestrationState


def _state_with_failed_verification(
    workspace_path: Path, *, retry_target: str | None, verification_retry_count: int = 0
) -> OrchestrationState:
    return {  # type: ignore[typeddict-item]
        "run_id": "r1",
        "thread_id": "r1-thread",
        "workspace_path": str(workspace_path),
        "query": "test",
        "intent": "build_plan",
        "profile_complete": True,
        "profile_valid": True,
        "hop_count": 3,
        "agent_trail": ["research", "fitness", "verification"],
        "approval_status": None,
        "revision_count": 0,
        "verification_retry_count": verification_retry_count,
        "last_capability_result": {
            "request_id": "12345678-1234-5678-1234-567812345678",
            "capability": "verification",
            "status": "completed",
            "artifacts": {"passed": False, "retry_target": retry_target},
        },
    }


def test_increments_retry_count_when_auto_retry_fires(tmp_path: Path) -> None:
    workspace_path = init_run_workspace("r1", workspace_root=tmp_path)
    state = _state_with_failed_verification(workspace_path, retry_target="research")

    updates = run_supervisor_routing_decision(state, max_hops=12, max_verification_retry_attempts=1)

    assert updates["next_agent"] == "research"
    assert updates["verification_retry_count"] == 1


def test_does_not_increment_retry_count_when_falling_through_to_hitl(tmp_path: Path) -> None:
    """Cap already exhausted -- routes to hitl, must not increment further."""
    workspace_path = init_run_workspace("r1", workspace_root=tmp_path)
    state = _state_with_failed_verification(
        workspace_path, retry_target="research", verification_retry_count=1
    )

    updates = run_supervisor_routing_decision(state, max_hops=12, max_verification_retry_attempts=1)

    assert updates["next_agent"] == "hitl"
    assert "verification_retry_count" not in updates


def test_does_not_increment_retry_count_for_unrelated_routing_decisions(tmp_path: Path) -> None:
    """A completely unrelated hop (planning -> fitness) must never touch this
    counter at all."""
    workspace_path = init_run_workspace("r2", workspace_root=tmp_path)
    state: OrchestrationState = {  # type: ignore[typeddict-item]
        "run_id": "r2",
        "thread_id": "r2-thread",
        "workspace_path": str(workspace_path),
        "query": "test",
        "intent": "build_plan",
        "profile_complete": True,
        "profile_valid": True,
        "hop_count": 1,
        "agent_trail": ["planning"],
        "approval_status": None,
        "revision_count": 0,
        "verification_retry_count": 0,
        "last_capability_result": {
            "request_id": "12345678-1234-5678-1234-567812345678",
            "capability": "planning",
            "status": "completed",
        },
    }

    updates = run_supervisor_routing_decision(state, max_hops=12, max_verification_retry_attempts=1)

    assert updates["next_agent"] == "fitness"
    assert "verification_retry_count" not in updates
