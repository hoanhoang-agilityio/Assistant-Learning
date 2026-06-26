from pathlib import Path

import pytest

from core.agents.state import OrchestrationState
from core.agents.tools import classify_request, read_global_state, route_subgraph
from core.graph.builder import build_graph
from core.graph.routing import resolve_next_subgraph, route_from_supervisor
from core.graph.run import create_initial_state


@pytest.fixture
def initial_state(tmp_path: Path) -> OrchestrationState:
    return create_initial_state(
        run_id="run-day2",
        thread_id="thread-day2",
        query="I want a 4-day training plan",
        workspace_root=tmp_path / "workspace",
    )


def test_classify_request_detects_training_plan() -> None:
    result = classify_request.invoke(
        {
            "query": "Create a 4-day training plan",
            "user_profile": {},
            "constraints": {},
        }
    )
    assert result["request_type"] == "training_plan"
    assert result["affected_domains"] == ["planning", "research", "fitness", "verify"]


def test_read_global_state_returns_orchestration_fields(initial_state: OrchestrationState) -> None:
    result = read_global_state.invoke({"state": initial_state})
    assert result["run_id"] == "run-day2"
    assert result["current_node"] == "supervisor"
    assert result["workspace_path"] == initial_state["workspace_path"]


def test_route_subgraph_returns_empty_dispatch_payload() -> None:
    result = route_subgraph.invoke(
        {
            "route_decision": None,
            "affected_domains": ["planning", "research", "fitness", "verify"],
            "current_node": "supervisor",
        }
    )
    assert result == {}


def test_resolve_next_subgraph_routes_to_planning(initial_state: OrchestrationState) -> None:
    classified = classify_request.invoke(
        {
            "query": initial_state["query"],
            "user_profile": initial_state["user_profile"],
            "constraints": initial_state["constraints"],
        }
    )
    state = {**initial_state, **classified}
    assert resolve_next_subgraph(state) == "planning"
    assert route_from_supervisor(state) == "planning"


def test_graph_compiles() -> None:
    graph = build_graph()
    assert graph is not None


def test_first_invoke_routes_to_planning(initial_state: OrchestrationState) -> None:
    graph = build_graph()
    config = {"configurable": {"thread_id": initial_state["thread_id"]}}
    result = graph.invoke(
        initial_state,
        config,
        interrupt_after=["planning"],
    )
    assert result["current_node"] == "planning"
    assert result["request_type"] == "training_plan"
