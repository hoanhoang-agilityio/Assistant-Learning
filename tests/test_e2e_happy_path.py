import json
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
from langgraph.types import Command

from core.agents.state import OrchestrationState
from core.config.settings import Settings, get_settings
from core.graph.builder import build_graph
from core.mcp.tavily_client import TavilyMCPClient
from core.observability.langfuse import (
    build_graph_invoke_config,
    build_langfuse_callbacks,
    create_trace_id_for_run,
    is_langfuse_enabled,
)
from core.subgraphs.verification.utils import FAITHFULNESS_PASS_THRESHOLD
from core.vfs import VFS


@pytest.fixture
def langfuse_settings() -> Settings:
    return Settings(
        langfuse_public_key="pk-test",
        langfuse_secret_key="sk-test",
        langfuse_base_url="http://localhost:3000",
    )


@pytest.fixture
def langfuse_disabled_settings() -> Settings:
    """Settings with Langfuse credentials absent.

    Deliberately built here rather than read from get_settings(): that cache is
    process-global, and RunOrchestrator's background threads (service.py spawns
    four of them, and several call get_settings()) can outlive the test that
    started them. When such a thread calls get_settings() after conftest's
    monkeypatched environment has been restored, it repopulates the lru_cache
    with this repo's real .env -- including live LANGFUSE_* keys -- and these
    assertions then see Langfuse *enabled*. That race made both tests below
    fail roughly one run in four.

    Constructing Settings directly reads the same monkeypatched environment
    without touching the shared cache, so the assertions are deterministic no
    matter what any leaked thread is doing.
    """
    return Settings(langfuse_public_key=None, langfuse_secret_key=None)


def test_is_langfuse_enabled_requires_keys(
    langfuse_settings: Settings, langfuse_disabled_settings: Settings
) -> None:
    assert is_langfuse_enabled(langfuse_settings) is True
    assert is_langfuse_enabled(langfuse_disabled_settings) is False


def test_build_langfuse_callbacks_empty_when_disabled(
    orchestration_state: OrchestrationState,
    langfuse_disabled_settings: Settings,
) -> None:
    assert (
        build_langfuse_callbacks(orchestration_state["run_id"], settings=langfuse_disabled_settings)
        == []
    )


@patch("core.observability.langfuse.CallbackHandler")
@patch("core.observability.langfuse.get_langfuse_client")
def test_build_langfuse_callbacks_uses_run_trace_id(
    mock_get_client: MagicMock,
    mock_callback_handler: MagicMock,
    orchestration_state: OrchestrationState,
    langfuse_settings: Settings,
) -> None:
    mock_client = MagicMock()
    mock_client.create_trace_id.return_value = "trace-from-run"
    mock_get_client.return_value = mock_client

    callbacks = build_langfuse_callbacks(
        orchestration_state["run_id"],
        settings=langfuse_settings,
    )

    mock_client.create_trace_id.assert_called_once_with(seed=orchestration_state["run_id"])
    mock_callback_handler.assert_called_once_with(
        trace_context={"trace_id": "trace-from-run"},
        update_trace=True,
    )
    assert len(callbacks) == 1


def test_create_trace_id_for_run_falls_back_to_run_id() -> None:
    assert create_trace_id_for_run("run-fallback", settings=get_settings()) == "run-fallback"


def test_build_graph_invoke_config_includes_thread_and_callbacks(
    orchestration_state: OrchestrationState,
    langfuse_settings: Settings,
) -> None:
    with (
        patch("core.observability.langfuse.build_langfuse_callbacks", return_value=["handler"]),
        patch(
            "core.observability.langfuse.create_trace_id_for_run",
            return_value="trace-from-run",
        ),
    ):
        config = build_graph_invoke_config(orchestration_state, settings=langfuse_settings)
    assert config["configurable"]["thread_id"] == orchestration_state["thread_id"]
    assert config["metadata"]["langfuse_session_id"] == orchestration_state["thread_id"]
    assert config["metadata"]["run_id"] == orchestration_state["run_id"]
    assert config["metadata"]["langfuse_trace_id"] == "trace-from-run"
    assert config["callbacks"] == ["handler"]


def test_e2e_happy_path_persists_final_artifact(
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

    # `interrupt_before=["hitl"]` pauses before the HITL node itself ever runs,
    # so `waiting_for_user` is not set yet -- readiness for approval is signaled
    # by the graph's next node, not a state field (see
    # core.graph.service._resolve_hitl_context, which reads `next_nodes` the
    # same way to build the approval message from the workspace directly).
    snapshot = graph.get_state(config)
    assert snapshot.next == ("hitl",)

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
    assert resumed["final_artifact_path"] is not None
    assert resumed["approval_status"] == "approved"

    vfs = VFS.for_run(Path(orchestration_state["workspace_path"]))
    assert vfs.exists("final/final_plan.md")
    assert vfs.exists("logs/persist_result.json")
    assert vfs.exists("logs/run_snapshot.json")
    assert vfs.exists("logs/metrics.json")
    assert vfs.exists("logs/token_cost.log")
    assert vfs.exists("logs/token_cost.md")

    persist_result = json.loads(vfs.read("logs/persist_result.json"))
    assert "final/final_plan.md" in persist_result["artifacts"]
    assert "final/workout.json" in persist_result["artifacts"]
    assert "final/blueprint.json" in persist_result["artifacts"]

    metrics = json.loads(vfs.read("logs/metrics.json"))
    assert metrics["faithfulness_score"] >= FAITHFULNESS_PASS_THRESHOLD
    assert metrics["verification_passed"] is True

    final_snapshot = graph.get_state(config)
    assert final_snapshot.next == ()
