"""The collection loop end to end: it completes when answered, and stops when it is not."""

import sys

import pytest
from langgraph.types import Command

import src.core.langgraph.nodes.intent as intent_node
import src.services.profile as profile_service
from src.core.configs.config import settings
from src.core.langgraph.graph import build_graph
from src.core.langgraph.nodes.extract_user_info import extract_user_info
from src.core.langgraph.nodes.user_info_exhausted import EXHAUSTED_INTRO
from src.core.langgraph.nodes.wait_for_user import MISSING_INFO_INTERRUPT
from src.core.langgraph.runtime.backends.memory import InMemoryRuntime
from src.schemas import initial_state
from src.services.profile import ProfileExtraction, flush_pending_saves
from tests.test_load_context import COMPLETE_PROFILE, USER_ID

extract_node = sys.modules[extract_user_info.__module__]

CONFIG = {"configurable": {"thread_id": "collection-loop"}}


@pytest.fixture
async def loop(monkeypatch: pytest.MonkeyPatch):
    """The real graph, on an in-process store and checkpointer, routed to coaching."""

    async def classify_as_coaching(_: str) -> str:
        return "coaching"

    runtime = InMemoryRuntime()
    monkeypatch.setattr(profile_service, "graph_runtime", runtime)
    monkeypatch.setattr(intent_node, "classify_user_intent", classify_as_coaching)

    yield build_graph().compile(
        checkpointer=await runtime.checkpointer(), name="collection_loop_test"
    )
    await runtime.close()


def _extracts(fields: dict):
    """Stand in for the LLM extractor with a fixed reading of the user's reply."""

    async def extract(_: str, fields_in_focus: list[str] | None = None) -> ProfileExtraction:
        return ProfileExtraction(**fields)

    return extract


def _asked_for_missing_info(result: dict) -> bool:
    """Whether the run is suspended at the missing-info gate specifically.

    ``coach_agent`` is not stubbed here — its own contract is covered in
    ``test_coach_agent.py`` and ``test_hitl_loop.py`` — so a complete profile may still
    suspend the run again, just at ``hitl_review`` rather than at the collection loop.
    """
    return any(
        interrupt.value.get("type") == MISSING_INFO_INTERRUPT
        for interrupt in result.get("__interrupt__", [])
    )


async def test_an_answered_question_completes_the_context(
    loop, monkeypatch: pytest.MonkeyPatch
) -> None:
    """One good reply and the branch exits to planning instead of asking again."""
    monkeypatch.setattr(
        extract_node, "extract_profile_fields", _extracts(COMPLETE_PROFILE)
    )

    suspended = await loop.ainvoke(initial_state("build me a plan", USER_ID), CONFIG)
    assert "__interrupt__" in suspended

    result = await loop.ainvoke(Command(resume="34, male, 178cm, 82kg, 4 days"), CONFIG)

    assert result["context_complete"] is True
    assert result["profile"] == COMPLETE_PROFILE
    assert not _asked_for_missing_info(result)


async def test_an_answer_persists_beyond_the_thread_it_was_given_in(
    loop, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The reply goes to long-term memory, so a new conversation never re-asks."""
    monkeypatch.setattr(
        extract_node, "extract_profile_fields", _extracts(COMPLETE_PROFILE)
    )
    await loop.ainvoke(initial_state("build me a plan", USER_ID), CONFIG)
    await loop.ainvoke(Command(resume="34, male, 178cm, 82kg, 4 days"), CONFIG)
    await flush_pending_saves()

    fresh = await loop.ainvoke(
        initial_state("build me a plan", USER_ID),
        {"configurable": {"thread_id": "second-conversation"}},
    )

    assert fresh["context_complete"] is True
    assert not _asked_for_missing_info(fresh)


async def test_a_partial_answer_only_asks_for_what_is_still_missing(
    loop, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Collection accumulates across rounds rather than restarting each time."""
    monkeypatch.setattr(extract_node, "extract_profile_fields", _extracts({"age": 34}))
    await loop.ainvoke(initial_state("build me a plan", USER_ID), CONFIG)

    result = await loop.ainvoke(Command(resume="I'm 34"), CONFIG)

    assert "age" not in result["missing_fields"]
    assert "goal" in result["missing_fields"]


async def test_an_unhelpful_user_is_asked_a_bounded_number_of_times(
    loop, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Without the counter this loop never terminates: ask, wait, extract, check, ask again."""
    monkeypatch.setattr(extract_node, "extract_profile_fields", _extracts({}))

    result = await loop.ainvoke(initial_state("build me a plan", USER_ID), CONFIG)
    asks = 1
    while "__interrupt__" in result:
        result = await loop.ainvoke(Command(resume="I'd rather not say"), CONFIG)
        asks += "__interrupt__" in result

    assert asks == settings.USER_INFO_MAX_RETRIES
    assert result["final_message"].startswith(EXHAUSTED_INTRO)
    assert (await loop.aget_state(CONFIG)).next == ()
