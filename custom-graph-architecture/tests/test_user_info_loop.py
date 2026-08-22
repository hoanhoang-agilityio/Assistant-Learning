"""The collection loop as a whole: it must end, even when the user never answers."""

import pytest
from langgraph.graph import END, START, StateGraph
from langgraph.types import Command

import src.core.langgraph.nodes.context as context_node
from src.core.configs.config import settings
from src.core.langgraph.nodes.context import (
    determine_context,
    load_context,
    route_after_context,
    route_after_determine_context,
)
from src.core.langgraph.nodes.request_missing_info import request_missing_info
from src.core.langgraph.nodes.user_info_exhausted import (
    EXHAUSTED_INTRO,
    user_info_exhausted,
)
from src.core.langgraph.nodes.wait_for_user import wait_for_user
from src.core.langgraph.runtime.backends.memory import InMemoryRuntime
from src.schemas import GraphState, initial_state
from src.services.profile import UserContext
from tests.test_load_context import USER_ID

CONFIG = {"configurable": {"thread_id": "collection-loop"}}


@pytest.fixture
async def graph(monkeypatch: pytest.MonkeyPatch):
    """The collection loop, wired around a user whose profile never fills in."""

    async def never_completes(_: str) -> UserContext:
        return UserContext(profile={"age": 34}, plan=None)

    monkeypatch.setattr(context_node, "load_user_context", never_completes)

    runtime = InMemoryRuntime()
    builder = StateGraph(GraphState)
    builder.add_node("load_context", load_context)
    builder.add_node("determine_context", determine_context)
    builder.add_node("request_missing_info", request_missing_info)
    builder.add_node("wait_for_user", wait_for_user)
    builder.add_node("user_info_exhausted", user_info_exhausted)

    builder.add_edge(START, "load_context")
    builder.add_conditional_edges(
        "load_context",
        route_after_context,
        {"complete": END, "incomplete": "determine_context"},
    )
    builder.add_conditional_edges(
        "determine_context",
        route_after_determine_context,
        {"ask": "request_missing_info", "exhausted": "user_info_exhausted"},
    )
    builder.add_edge("request_missing_info", "wait_for_user")
    builder.add_edge("wait_for_user", "load_context")
    builder.add_edge("user_info_exhausted", END)

    yield builder.compile(
        checkpointer=await runtime.checkpointer(), name="collection_loop_test"
    )
    await runtime.close()


async def test_an_unhelpful_user_is_asked_a_bounded_number_of_times(graph) -> None:
    """Without the counter this loop never terminates: ask, wait, reload, ask again."""
    result = await graph.ainvoke(initial_state("build me a plan", USER_ID), CONFIG)

    asks = 1
    while "__interrupt__" in result:
        result = await graph.ainvoke(Command(resume="I'd rather not say"), CONFIG)
        asks += "__interrupt__" in result

    assert asks == settings.USER_INFO_MAX_RETRIES
    assert result["user_info_retry_count"] == settings.USER_INFO_MAX_RETRIES


async def test_the_loop_ends_by_telling_the_user_why(graph) -> None:
    """The run stops with a refusal, not with silence or a plan built on guesses."""
    result = await graph.ainvoke(initial_state("build me a plan", USER_ID), CONFIG)
    while "__interrupt__" in result:
        result = await graph.ainvoke(Command(resume="I'd rather not say"), CONFIG)

    assert result["final_message"].startswith(EXHAUSTED_INTRO)
    assert (await graph.aget_state(CONFIG)).next == ()
