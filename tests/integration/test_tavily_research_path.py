import json
from pathlib import Path

from core.capabilities.research.capability import invoke_research_capability
from core.mcp.tavily_client import TavilyMCPClient
from core.orchestration.agents.execution_context import build_execution_context
from core.orchestration.agents.state import OrchestrationState
from core.orchestration.graph.run import create_initial_state
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
    ctx = build_execution_context(intent="build_plan")
    orchestration_state: OrchestrationState = {
        **state,
        "execution_context": ctx.model_dump(mode="json"),
    }
    updates = invoke_research_capability(orchestration_state)
    assert updates.get("run_complete") is not True
    vfs = VFS.for_run(Path(state["workspace_path"]))
    assert vfs.exists("research/sources.json")
    assert vfs.exists("research/findings.json")
    sources = json.loads(vfs.read("research/sources.json"))
    findings = json.loads(vfs.read("research/findings.json"))
    assert len(sources) >= 1
    assert "evidence" in findings
    assert "structured_findings" in findings
    assert findings["structured_findings"]["consensus"]
