"""The collection loop end to end: it completes when answered, and stops when it is not."""

import sys

import pytest
from langgraph.graph import END, START, StateGraph
from langgraph.types import Command

import src.services.profile as profile_service
from src.core.configs.config import settings
from src.core.langgraph.nodes.context import (
    determine_context,
    load_context,
    route_after_context,
    route_after_determine_context,
)
from src.core.langgraph.nodes.request_missing_info import request_missing_info
from src.core.langgraph.nodes.save_user_data import save_user_data
from src.core.langgraph.nodes.user_info_exhausted import (
    EXHAUSTED_INTRO,
    user_info_exhausted,
)
from src.core.langgraph.nodes.wait_for_user import wait_for_user
from src.core.langgraph.runtime.backends.memory import InMemoryRuntime
from src.schemas import GraphState, initial_state
from tests.test_load_context import COMPLETE_PROFILE, USER_ID

save_node = sys.modules[save_user_data.__module__]

CONFIG = {"configurable": {"thread_id": "collection-loop"}}


@pytest.fixture
async def loop(monkeypatch: pytest.MonkeyPatch):
    """The whole collection branch, on an in-process store and checkpointer."""
    runtime = InMemoryRuntime()
    monkeypatch.setattr(profile_service, "graph_runtime", runtime)

    builder = StateGraph(GraphState)
    builder.add_node("load_context", load_context)
    builder.add_node("determine_context", determine_context)
    builder.add_node("request_missing_info", request_missing_info)
    builder.add_node("wait_for_user", wait_for_user)
    builder.add_node("save_user_data", save_user_data)
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
    builder.add_edge("wait_for_user", "save_user_data")
    builder.add_edge("save_user_data", "load_context")
    builder.add_edge("user_info_exhausted", END)

    yield builder.compile(
        checkpointer=await runtime.checkpointer(), name="collection_loop_test"
    )
    await runtime.close()


def _extracts(fields: dict):
    """Stand in for the LLM extractor with a fixed reading of the user's reply."""

    async def extract(_: str) -> dict:
        return fields

    return extract


async def test_an_answered_question_completes_the_context(
    loop, monkeypatch: pytest.MonkeyPatch
) -> None:
    """One good reply and the branch exits to planning instead of asking again."""
    monkeypatch.setattr(
        save_node, "extract_profile_fields", _extracts(COMPLETE_PROFILE)
    )

    suspended = await loop.ainvoke(initial_state("build me a plan", USER_ID), CONFIG)
    assert "__interrupt__" in suspended

    result = await loop.ainvoke(Command(resume="34, male, 178cm, 82kg, 4 days"), CONFIG)

    assert result["context_complete"] is True
    assert result["profile"] == COMPLETE_PROFILE
    assert (await loop.aget_state(CONFIG)).next == ()


async def test_an_answer_persists_beyond_the_thread_it_was_given_in(
    loop, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The reply goes to long-term memory, so a new conversation never re-asks."""
    monkeypatch.setattr(
        save_node, "extract_profile_fields", _extracts(COMPLETE_PROFILE)
    )
    await loop.ainvoke(initial_state("build me a plan", USER_ID), CONFIG)
    await loop.ainvoke(Command(resume="34, male, 178cm, 82kg, 4 days"), CONFIG)

    fresh = await loop.ainvoke(
        initial_state("build me a plan", USER_ID),
        {"configurable": {"thread_id": "second-conversation"}},
    )

    assert fresh["context_complete"] is True
    assert "__interrupt__" not in fresh


async def test_a_partial_answer_only_asks_for_what_is_still_missing(
    loop, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Collection accumulates across rounds rather than restarting each time."""
    monkeypatch.setattr(save_node, "extract_profile_fields", _extracts({"age": 34}))
    await loop.ainvoke(initial_state("build me a plan", USER_ID), CONFIG)

    result = await loop.ainvoke(Command(resume="I'm 34"), CONFIG)

    assert "age" not in result["missing_fields"]
    assert "goal" in result["missing_fields"]


async def test_an_unhelpful_user_is_asked_a_bounded_number_of_times(
    loop, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Without the counter this loop never terminates: ask, wait, save, reload, ask again."""
    monkeypatch.setattr(save_node, "extract_profile_fields", _extracts({}))

    result = await loop.ainvoke(initial_state("build me a plan", USER_ID), CONFIG)
    asks = 1
    while "__interrupt__" in result:
        result = await loop.ainvoke(Command(resume="I'd rather not say"), CONFIG)
        asks += "__interrupt__" in result

    assert asks == settings.USER_INFO_MAX_RETRIES
    assert result["final_message"].startswith(EXHAUSTED_INTRO)
    assert (await loop.aget_state(CONFIG)).next == ()
