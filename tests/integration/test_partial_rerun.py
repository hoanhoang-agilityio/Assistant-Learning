import json
from pathlib import Path

import pytest

from core.agents.state import OrchestrationState
from core.agents.supervisor import supervisor_node
from core.graph.routing import route_from_supervisor
from core.graph.run import create_initial_state
from core.vfs import VFS


@pytest.fixture
def failed_verification_state(workspace_root: Path, complete_profile: dict) -> OrchestrationState:
    state = create_initial_state(
        run_id="rerun-run",
        thread_id="rerun-thread",
        query="Fix my training plan",
        user_profile=complete_profile,
        workspace_root=workspace_root,
    )
    vfs = VFS.for_run(Path(state["workspace_path"]))
    report = {
        "passed": False,
        "citation": {"passed": True, "issues": []},
        "consistency": {"passed": True, "issues": []},
        "safety": {"passed": False, "issues": ["aggressive_calorie_deficit"]},
        "ragas": {"pass_fail": True, "faithfulness_score": 0.95},
        "feedback": "safety issue",
    }
    vfs.write("verify/verification_v1.json", json.dumps(report))
    return {
        **state,
        "request_type": "fat_loss",
        "affected_domains": ["planning", "research", "fitness", "verify"],
        "current_node": "verification",
        "verification_passed": False,
        "faithfulness_score": 0.95,
        "retry_count": 0,
        "replan_count": 0,
    }


def test_partial_rerun_routes_fix_reasoning_to_fitness(
    failed_verification_state: OrchestrationState,
) -> None:
    updates = supervisor_node(failed_verification_state)
    merged: OrchestrationState = {**failed_verification_state, **updates}
    assert updates["route_decision"] == "FIX_REASONING"
    assert route_from_supervisor(merged) == "fitness"
