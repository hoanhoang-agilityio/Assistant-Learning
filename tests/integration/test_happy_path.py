import json
from pathlib import Path

from langgraph.types import Command

from core.adapters.mcp.tavily_client import TavilyMCPClient
from core.adapters.vfs import VFS
from core.capabilities.verification.utils import FAITHFULNESS_PASS_THRESHOLD
from core.orchestration.graph.builder import build_graph
from core.orchestration.state import OrchestrationState


def test_integration_happy_path_hitl_to_persist(
    orchestration_state: OrchestrationState,
    memory_checkpointer,
    mock_tavily_client: TavilyMCPClient,
) -> None:
    del mock_tavily_client
    graph = build_graph(checkpointer=memory_checkpointer)
    config = {"configurable": {"thread_id": orchestration_state["thread_id"]}}

    paused = graph.invoke(orchestration_state, config)
    assert paused["verification_passed"] is True
    assert paused["faithfulness_score"] >= FAITHFULNESS_PASS_THRESHOLD
    assert graph.get_state(config).next == ("hitl",)

    resumed = graph.invoke(
        Command(
            update={
                "user_response": "approve",
                "approval_status": "approved",
                "waiting_for_user": False,
            }
        ),
        config,
    )
    assert resumed["current_node"] == "persist"
    vfs = VFS.for_run(Path(orchestration_state["workspace_path"]))
    assert vfs.exists("final/final_plan.md")
    assert json.loads(vfs.read("logs/metrics.json"))["verification_passed"] is True
