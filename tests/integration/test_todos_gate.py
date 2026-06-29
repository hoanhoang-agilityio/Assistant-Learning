from pathlib import Path

from core.agents.state import OrchestrationState
from core.graph.run import create_initial_state
from core.subgraphs.research.graph import invoke_research_subgraph
from core.vfs import VFS


def test_research_blocked_without_planning_todos(workspace_root: Path) -> None:
    state = create_initial_state(
        run_id="gate-run",
        thread_id="gate-thread",
        query="Research strength training evidence",
        workspace_root=workspace_root,
    )
    orchestration_state: OrchestrationState = {
        **state,
        "request_type": "training_plan",
        "affected_domains": ["planning", "research", "fitness", "verify"],
    }
    updates = invoke_research_subgraph(orchestration_state)
    assert updates["waiting_for_user"] is True
    vfs = VFS.for_run(Path(state["workspace_path"]))
    assert not vfs.exists("research/sources.json")
