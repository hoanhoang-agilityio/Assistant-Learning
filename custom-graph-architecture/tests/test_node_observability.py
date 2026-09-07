"""Tests for node instrumentation: what a run records, and what recording must never cost.

Two rules these hold. Every node the graph runs is instrumented, because instrumenting
twenty of twenty-one leaves exactly the gap an incident falls into. And tracing is
best-effort: a Langfuse that is down, unconfigured or throwing must leave the turn intact.
"""

from typing import Any
from unittest.mock import MagicMock

import pytest
from langgraph.errors import GraphInterrupt

from src.enums import Node
from src.graph import NODES, build_graph
from src.observability import nodes as observability
from src.observability.nodes import observations, observed
from src.schemas import GraphState, initial_state

STATE: GraphState = initial_state("build me a plan", "user-1")

PASSAGES = [
    {"text": "Protein.", "source": "Nutrition", "score": 0.91},
    {"text": "Creatine.", "source": "Nutrition", "score": 0.72},
]

FAILED_VERIFICATION = {
    "issues": [
        {"check": "macros", "severity": "error", "message": "calories drift"},
        {"check": "volume", "severity": "error", "message": "too many sets"},
        {"check": "macros", "severity": "error", "message": "protein low"},
    ]
}


@pytest.fixture
def client(monkeypatch: pytest.MonkeyPatch) -> MagicMock:
    """A stand-in Langfuse client, so span and score writes are observable."""
    fake = MagicMock()
    monkeypatch.setattr(observability, "get_langfuse_client", lambda: fake)
    return fake


@pytest.fixture
def no_client(monkeypatch: pytest.MonkeyPatch) -> None:
    """A process where tracing never came up, which is every dev machine without keys."""
    monkeypatch.setattr(observability, "get_langfuse_client", lambda: None)


def _node(update: dict[str, Any]):
    """A node that returns a fixed update."""

    async def run(_state: GraphState) -> dict[str, Any]:
        return update

    return run


def _failing_node(error: BaseException):
    """A node that raises."""

    async def run(_state: GraphState) -> dict[str, Any]:
        raise error

    return run


# --- What a node update is worth recording ------------------------------------------------


def test_the_routing_label_and_retry_counters_are_recorded() -> None:
    """Spec §10 names the routing decision and the retry counts as searchable trace fields."""
    fields = observations({"next": "coach_agent", "coach_retry_count": 2})

    assert fields == {"next": "coach_agent", "coach_retry_count": 2}


def test_state_a_node_did_not_write_is_not_reported_as_its_decision() -> None:
    """Read off the update, not the state: a line says what *this* node decided."""
    assert observations({"profile": {"age": 34}}) == {}


def test_a_passing_verification_records_the_verdict() -> None:
    """``verification_result: None`` is the gate passing, not the gate being unreported."""
    assert observations({"verification_result": None}) == {"verification_passed": True}


def test_a_failed_verification_records_which_checks_failed_not_their_prose() -> None:
    """The failed check names are what a dashboard groups by; the messages are for the agent."""
    fields = observations({"verification_result": FAILED_VERIFICATION})

    assert fields == {
        "verification_passed": False,
        "verification_issue_count": 3,
        "verification_failed_checks": ["macros", "volume"],
    }


def test_retrieval_records_its_similarity_scores() -> None:
    """The scores are what the retrieval threshold is tuned against, so they must be kept."""
    fields = observations({"retrieved_context": PASSAGES})

    assert fields == {
        "retrieved_chunks": 2,
        "retrieval_scores": [0.91, 0.72],
        "retrieval_top_score": 0.91,
    }


def test_retrieving_nothing_is_recorded_as_a_zero_not_as_silence() -> None:
    """An empty retrieval is the fallback's whole cause; a missing field would hide it."""
    assert observations({"retrieved_context": []}) == {"retrieved_chunks": 0}


def test_the_plan_is_recorded_as_generated_rather_than_in_full() -> None:
    """A whole training plan on every span is cost and noise; its existence is the signal."""
    fields = observations({"plan": {"template_id": "tpl-1"}})

    assert fields == {"plan_generated": True}


# --- Latency and outcome ------------------------------------------------------------------


async def test_a_node_is_timed_and_its_update_passes_through_untouched(client) -> None:
    """Instrumentation observes; a node that returned something else would be a bug in it."""
    update = {"next": "qa_agent"}

    assert await observed(Node.SUPERVISOR, _node(update))(STATE) == update

    metadata = client.update_current_span.call_args.kwargs["metadata"]
    assert metadata["node"] == Node.SUPERVISOR.value
    assert metadata["duration_ms"] >= 0
    assert metadata["next"] == "qa_agent"


async def test_a_failing_node_is_recorded_as_an_error_and_still_raises(client) -> None:
    """Swallowing the failure here would let a broken node look like a quiet one."""
    with pytest.raises(RuntimeError):
        await observed(Node.COACH_AGENT, _failing_node(RuntimeError("boom")))(STATE)

    assert client.update_current_span.call_args.kwargs["level"] == "ERROR"
    assert "boom" in client.update_current_span.call_args.kwargs["status_message"]


async def test_a_pause_is_not_recorded_as_a_failure(client) -> None:
    """``interrupt()`` parks the run by raising; every HITL turn would read as an error."""
    with pytest.raises(GraphInterrupt):
        await observed(Node.PLAN_APPROVAL, _failing_node(GraphInterrupt(())))(STATE)

    client.update_current_span.assert_not_called()


# --- The two gate results, promoted to trace scores ----------------------------------------


async def test_the_faithfulness_score_is_promoted_to_a_trace_score(client) -> None:
    """A score Langfuse can chart is the point of scoring the answer at all."""
    await observed(Node.VERIFY_FAITHFULNESS, _node({"faithfulness_score": 0.94}))(STATE)

    assert client.score_current_trace.call_args.kwargs == {
        "name": "faithfulness",
        "value": 0.94,
        "data_type": "NUMERIC",
    }


async def test_an_unscorable_answer_is_not_charted_as_a_zero(client) -> None:
    """RAGAS returns nothing when there is no statement to judge; 0.0 would read as unfaithful."""
    await observed(Node.VERIFY_FAITHFULNESS, _node({"faithfulness_score": None}))(STATE)

    client.score_current_trace.assert_not_called()


async def test_the_verification_verdict_is_promoted_to_a_trace_score(client) -> None:
    """Pass rate over time is the number that says whether the coach prompt is working."""
    await observed(
        Node.DETERMINISTIC_VERIFICATION, _node({"verification_result": None})
    )(STATE)

    assert client.score_current_trace.call_args.kwargs == {
        "name": "plan_verification",
        "value": 1.0,
        "data_type": "BOOLEAN",
    }


# --- Tracing never breaks a turn ----------------------------------------------------------


async def test_a_node_runs_normally_when_tracing_never_came_up(no_client) -> None:
    """No Langfuse keys is the default on a dev machine, and must cost nothing."""
    assert await observed(Node.SUPERVISOR, _node({"next": "qa_agent"}))(STATE) == {
        "next": "qa_agent"
    }


async def test_a_throwing_langfuse_client_does_not_take_the_node_with_it(
    client,
) -> None:
    """Tracing is best-effort. A trace backend outage is not a reason to fail a turn."""
    client.update_current_span.side_effect = ConnectionError("langfuse down")
    client.score_current_trace.side_effect = ConnectionError("langfuse down")

    assert await observed(
        Node.VERIFY_FAITHFULNESS, _node({"faithfulness_score": 0.94})
    )(STATE) == {"faithfulness_score": 0.94}


# --- The graph-level guarantee ------------------------------------------------------------


def test_every_node_in_the_graph_is_listed_exactly_once() -> None:
    """A node added outside ``NODES`` is a node that runs with no timing and no trace."""
    listed = [name for name, _ in NODES]

    assert sorted(listed) == sorted(Node)
    assert len(listed) == len(set(listed))


@pytest.mark.parametrize("name", sorted(Node))
def test_the_graph_runs_the_instrumented_node_not_the_bare_one(name: Node) -> None:
    """Instrumenting twenty of twenty-one leaves the gap an incident falls into."""
    node = build_graph().nodes[name.value].runnable.afunc

    assert hasattr(node, "__wrapped__")
