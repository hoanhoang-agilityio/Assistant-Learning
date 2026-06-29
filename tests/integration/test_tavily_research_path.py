import json
from pathlib import Path

from core.agents.state import OrchestrationState
from core.graph.run import create_initial_state
from core.mcp.tavily_client import TavilyMCPClient
from core.subgraphs.planning.utils import write_planning_todos
from core.subgraphs.research.graph import invoke_research_subgraph
from core.vfs import VFS


def test_tavily_research_path_writes_artifacts(
    workspace_root: Path,
    complete_profile: dict,
    mock_tavily_client: TavilyMCPClient,
) -> None:
    del mock_tavily_client
    state = create_initial_state(
        run_id="research-run",
        thread_id="research-thread",
        query="Collect hypertrophy evidence for fat loss programming.",
        user_profile=complete_profile,
        workspace_root=workspace_root,
    )
    write_planning_todos(complete_profile, "fat_loss", state["workspace_path"])
    orchestration_state: OrchestrationState = {
        **state,
        "request_type": "fat_loss",
        "affected_domains": ["planning", "research", "fitness", "verify"],
    }
    updates = invoke_research_subgraph(orchestration_state)
    assert updates["waiting_for_user"] is False
    vfs = VFS.for_run(Path(state["workspace_path"]))
    assert vfs.exists("research/sources.json")
    assert vfs.exists("research/findings.json")
    sources = json.loads(vfs.read("research/sources.json"))
    findings = json.loads(vfs.read("research/findings.json"))
    assert len(sources) >= 1
    assert findings["source_count"] >= 1
    assert "evidence" in findings
