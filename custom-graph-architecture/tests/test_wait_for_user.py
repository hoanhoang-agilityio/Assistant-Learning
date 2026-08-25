"""Tests for the ``wait_for_user`` interrupt gate."""

from typing import Any

import pytest
from langchain_core.messages import HumanMessage
from langgraph.graph import END, START, StateGraph
from langgraph.types import Command

from src.core.langgraph.nodes.request_missing_info import (
    build_missing_info_request,
    request_missing_info,
)
from src.core.langgraph.nodes.wait_for_user import MISSING_INFO_INTERRUPT, wait_for_user
from src.core.langgraph.runtime.backends.memory import InMemoryRuntime
from src.schemas import GraphState, initial_state
from tests.test_load_context import USER_ID

MISSING = ["goal", "training_days_per_week"]


@pytest.fixture
async def graph():
    """The ask-and-wait pair, compiled on a checkpointer that can hold a suspended run."""
    runtime = InMemoryRuntime()
    builder = StateGraph(GraphState)
    builder.add_node("request_missing_info", request_missing_info)
    builder.add_node("wait_for_user", wait_for_user)
    builder.add_edge(START, "request_missing_info")
    builder.add_edge("request_missing_info", "wait_for_user")
    builder.add_edge("wait_for_user", END)

    yield builder.compile(
        checkpointer=await runtime.checkpointer(), name="wait_for_user_test"
    )
    await runtime.close()


def _config(thread_id: str) -> dict[str, Any]:
    """Address one conversation's checkpoint."""
    return {"configurable": {"thread_id": thread_id}}


def _start(missing_fields: list[str] = MISSING) -> GraphState:
    """A run that has already been routed here by an incomplete profile."""
    return initial_state("build me a plan", USER_ID) | {
        "missing_fields": missing_fields
    }


async def test_the_run_suspends_instead_of_finishing(graph) -> None:
    """The graph stops at the gate rather than planning from an incomplete profile."""
    config = _config("suspend")

    await graph.ainvoke(_start(), config)

    assert (await graph.aget_state(config)).next == ("wait_for_user",)


async def test_the_interrupt_tells_the_caller_what_is_needed(graph) -> None:
    """The payload carries both the fields to collect and the text to show."""
    suspended = await graph.ainvoke(_start(), _config("payload"))

    assert suspended["__interrupt__"][0].value == {
        "type": MISSING_INFO_INTERRUPT,
        "missing_fields": MISSING,
        "message": build_missing_info_request(MISSING),
    }


async def test_the_interrupt_is_labelled_for_its_gate(graph) -> None:
    """Two gates suspend this graph; a caller must be able to tell them apart."""
    suspended = await graph.ainvoke(_start(), _config("labelled"))

    assert suspended["__interrupt__"][0].value["type"] == MISSING_INFO_INTERRUPT


async def test_the_answer_becomes_the_next_turn_of_the_conversation(graph) -> None:
    """``extract_user_info`` reads the reply off the end of ``messages``."""
    config = _config("resume")
    await graph.ainvoke(_start(), config)

    resumed = await graph.ainvoke(
        Command(resume="  I train 4 days, fat loss  "), config
    )

    assert isinstance(resumed["messages"][-1], HumanMessage)
    assert resumed["messages"][-1].content == "I train 4 days, fat loss"


async def test_the_question_asked_survives_in_the_transcript(graph) -> None:
    """The reply is only readable in context if the question is still above it."""
    config = _config("transcript")
    await graph.ainvoke(_start(), config)

    resumed = await graph.ainvoke(Command(resume="fat loss, 4 days"), config)

    assert resumed["messages"][-2].content == build_missing_info_request(MISSING)


async def test_a_structured_answer_is_still_recorded(graph) -> None:
    """A client resuming with fields instead of prose must not break the run."""
    config = _config("structured")
    await graph.ainvoke(_start(), config)

    resumed = await graph.ainvoke(Command(resume={"goal": "fat loss"}), config)

    assert "fat loss" in resumed["messages"][-1].content


async def test_the_run_finishes_once_answered(graph) -> None:
    """Resuming clears the gate rather than suspending a second time."""
    config = _config("finish")
    await graph.ainvoke(_start(), config)

    await graph.ainvoke(Command(resume="34, male, 178cm, 82kg"), config)

    assert (await graph.aget_state(config)).next == ()


async def test_two_conversations_suspend_independently(graph) -> None:
    """The gate is checkpointed per thread; one user's answer must not resume another's."""
    first, second = _config("thread-a"), _config("thread-b")
    await graph.ainvoke(_start(), first)
    await graph.ainvoke(_start(["age"]), second)

    await graph.ainvoke(Command(resume="fat loss, 4 days"), first)

    assert (await graph.aget_state(first)).next == ()
    assert (await graph.aget_state(second)).next == ("wait_for_user",)
