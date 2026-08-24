"""Tests for the ``hitl_review`` interrupt gate."""

from typing import Any

import pytest
from langchain_core.messages import HumanMessage
from langgraph.graph import END, START, StateGraph
from langgraph.types import Command

from src.core.langgraph.nodes.hitl_review import HITL_REVIEW_INTERRUPT, hitl_review
from src.core.langgraph.runtime.backends.memory import InMemoryRuntime
from src.schemas import GraphState, initial_state
from tests.test_load_context import USER_ID

PLAN = {"goal": "fat_loss", "training_days_per_week": 4}


@pytest.fixture
async def graph():
    """A single-node graph that suspends at the review gate."""
    runtime = InMemoryRuntime()
    builder = StateGraph(GraphState)
    builder.add_node("hitl_review", hitl_review)
    builder.add_edge(START, "hitl_review")
    builder.add_edge("hitl_review", END)

    yield builder.compile(
        checkpointer=await runtime.checkpointer(), name="hitl_review_test"
    )
    await runtime.close()


def _config(thread_id: str) -> dict[str, Any]:
    """Address one conversation's checkpoint."""
    return {"configurable": {"thread_id": thread_id}}


def _start() -> GraphState:
    """A run that reached the gate with a plan already generated and verified."""
    return initial_state("build me a plan", USER_ID) | {"plan": PLAN}


async def test_the_run_suspends_instead_of_finishing(graph) -> None:
    """The graph stops at the gate rather than handing the plan straight back."""
    config = _config("suspend")

    await graph.ainvoke(_start(), config)

    assert (await graph.aget_state(config)).next == ("hitl_review",)


async def test_the_interrupt_carries_the_plan_to_review(graph) -> None:
    """The caller needs the plan itself to show the user what they're approving."""
    suspended = await graph.ainvoke(_start(), _config("payload"))

    interrupt_value = suspended["__interrupt__"][0].value
    assert interrupt_value["type"] == HITL_REVIEW_INTERRUPT
    assert interrupt_value["plan"] == PLAN


async def test_an_approval_is_recorded_with_no_feedback(graph) -> None:
    """Approving needs nothing further from the user."""
    config = _config("approve")
    await graph.ainvoke(_start(), config)

    resumed = await graph.ainvoke(Command(resume="approve"), config)

    assert resumed["hitl_decision"] == "approve"
    assert resumed["hitl_feedback"] is None


async def test_a_structured_approval_is_recognised(graph) -> None:
    """A client resuming with a decision object instead of prose must still approve."""
    config = _config("structured-approve")
    await graph.ainvoke(_start(), config)

    resumed = await graph.ainvoke(Command(resume={"decision": "approve"}), config)

    assert resumed["hitl_decision"] == "approve"
    assert resumed["hitl_feedback"] is None


async def test_a_structured_rejection_keeps_its_feedback(graph) -> None:
    """The coach agent needs the reviewer's actual words to revise the plan."""
    config = _config("structured-reject")
    await graph.ainvoke(_start(), config)

    resumed = await graph.ainvoke(
        Command(resume={"decision": "reject", "feedback": "too much volume on day 1"}),
        config,
    )

    assert resumed["hitl_decision"] == "reject"
    assert resumed["hitl_feedback"] == "too much volume on day 1"


async def test_free_text_that_is_not_an_approval_is_a_rejection_with_feedback(
    graph,
) -> None:
    """A reviewer typing a comment instead of a keyword is rejecting with that comment."""
    config = _config("free-text-reject")
    await graph.ainvoke(_start(), config)

    resumed = await graph.ainvoke(Command(resume="swap the bench press"), config)

    assert resumed["hitl_decision"] == "reject"
    assert resumed["hitl_feedback"] == "swap the bench press"


async def test_a_rejection_with_no_feedback_leaves_it_none(graph) -> None:
    """No feedback is a distinct case from feedback that happens to be empty."""
    config = _config("no-feedback")
    await graph.ainvoke(_start(), config)

    resumed = await graph.ainvoke(Command(resume={"decision": "reject"}), config)

    assert resumed["hitl_decision"] == "reject"
    assert resumed["hitl_feedback"] is None


async def test_the_decision_is_recorded_in_the_transcript(graph) -> None:
    """The reviewer's reply becomes part of the conversation, like any other turn."""
    config = _config("transcript")
    await graph.ainvoke(_start(), config)

    resumed = await graph.ainvoke(Command(resume="swap the bench press"), config)

    assert isinstance(resumed["messages"][-1], HumanMessage)
    assert resumed["messages"][-1].content == "swap the bench press"


async def test_the_run_finishes_once_reviewed(graph) -> None:
    """Resuming clears the gate rather than suspending a second time."""
    config = _config("finish")
    await graph.ainvoke(_start(), config)

    await graph.ainvoke(Command(resume="approve"), config)

    assert (await graph.aget_state(config)).next == ()
