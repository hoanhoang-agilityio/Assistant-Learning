"""The graph's shape, checked against the edge table in the implementation spec."""

import pytest
from langgraph.graph import END, START

from src.core.langgraph.graph import build_graph

# Nodes implemented so far. The rest of the spec's table arrives with later milestones.
EXPECTED_NODES = {
    "llm_guard",
    "blocked",
    "classify_intent",
    "off_topic",
    "load_context",
    "determine_context",
    "request_missing_info",
    "wait_for_user",
    "save_user_data",
    "user_info_exhausted",
    "write_todo",
}

# (from, condition, to) — ``None`` where the edge is unconditional.
EXPECTED_EDGES = {
    (START, None, "llm_guard"),
    ("llm_guard", "blocked", "blocked"),
    ("llm_guard", "pass", "classify_intent"),
    ("classify_intent", "coaching", "load_context"),
    ("classify_intent", "off_topic", "off_topic"),
    ("load_context", "incomplete", "determine_context"),
    ("load_context", "complete", "write_todo"),
    ("determine_context", "ask", "request_missing_info"),
    ("determine_context", "exhausted", "user_info_exhausted"),
    ("request_missing_info", None, "wait_for_user"),
    ("wait_for_user", None, "save_user_data"),
    ("save_user_data", None, "load_context"),
    ("blocked", None, END),
    ("off_topic", None, END),
    ("user_info_exhausted", None, END),
    ("write_todo", None, END),
}


@pytest.fixture(scope="module")
def graph():
    """The compiled graph's own view of its nodes and edges."""
    return build_graph().compile(name="wiring_test").get_graph()


@pytest.fixture(scope="module")
def edges(graph) -> set[tuple[str, str | None, str]]:
    """Every edge as ``(from, condition, to)``.

    LangGraph drops the branch label when it matches the target node's name, so a
    conditional edge with no label is restored to the name it routed on.
    """
    return {
        (
            edge.source,
            (edge.data or edge.target) if edge.conditional else None,
            edge.target,
        )
        for edge in graph.edges
    }


def test_every_implemented_node_is_in_the_graph(graph) -> None:
    """A node that exists but is never added is dead code the tests would still pass."""
    assert EXPECTED_NODES <= set(graph.nodes)


@pytest.mark.parametrize("edge", sorted(EXPECTED_EDGES, key=str))
def test_the_spec_edge_exists(edges, edge: tuple[str, str | None, str]) -> None:
    """Each row of the spec's edge table, for the nodes built so far."""
    assert edge in edges


def test_the_context_branch_has_no_edges_beyond_the_spec(edges) -> None:
    """An extra route out of the collection loop would be a way to skip the profile gate."""
    context_nodes = EXPECTED_NODES - {
        "llm_guard",
        "blocked",
        "classify_intent",
        "off_topic",
    }
    actual = {edge for edge in edges if edge[0] in context_nodes}

    assert actual == {edge for edge in EXPECTED_EDGES if edge[0] in context_nodes}


def test_the_collection_loop_returns_to_the_reload(edges) -> None:
    """``save_user_data`` must route back through ``load_context``, not straight to planning."""
    assert ("save_user_data", None, "load_context") in edges
    assert not [
        edge
        for edge in edges
        if edge[0] == "save_user_data" and edge[2] != "load_context"
    ]


def test_a_complete_profile_goes_to_planning(edges) -> None:
    """The profile gate's whole purpose: a complete profile is what opens the coach branch."""
    assert ("load_context", "complete", "write_todo") in edges


def test_the_coach_agent_is_still_unbuilt(edges) -> None:
    """A written todo ends the run until ``coach_agent`` exists in task 4.2."""
    assert ("write_todo", None, END) in edges
