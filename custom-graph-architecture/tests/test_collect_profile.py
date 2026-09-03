"""Tests for the ``collect_profile`` node: one form, validated, saved once."""

import sys
from typing import Any

import pytest
from langgraph.graph import END, START, StateGraph
from langgraph.types import Command

from src.nodes.collect_profile import (
    PROFILE_FORM_INTERRUPT,
    PROFILE_SAVED_MESSAGE,
    collect_profile,
)
from src.runtime.backends.memory import InMemoryRuntime
from src.schemas import GraphState, initial_state

collect_profile_module = sys.modules[collect_profile.__module__]

USER_ID = "user-1"

COMPLETE = {
    "age": 27,
    "sex": "MALE",
    "height_cm": 178.0,
    "current_weight_kg": 80.0,
    "activity_level": "MODERATE",
    "goal": "FAT_LOSS",
    "training_days_per_week": 4,
}


@pytest.fixture
def saved(monkeypatch: pytest.MonkeyPatch) -> list[dict]:
    """Record every write the node makes, instead of reaching long-term memory."""
    writes: list[dict] = []

    async def save_profile(_user_id: str, updates: dict) -> dict:
        writes.append(updates)
        return updates

    monkeypatch.setattr(collect_profile_module, "save_profile", save_profile)
    return writes


@pytest.fixture
async def graph():
    """A single-node graph that suspends on the form."""
    runtime = InMemoryRuntime()
    builder = StateGraph(GraphState)
    builder.add_node("collect_profile", collect_profile)
    builder.add_edge(START, "collect_profile")
    builder.add_edge("collect_profile", END)

    yield builder.compile(
        checkpointer=await runtime.checkpointer(), name="collect_profile_test"
    )
    await runtime.close()


def _start(profile: dict | None = None, draft: dict | None = None) -> GraphState:
    """A run that reached the node with the coach unable to plan."""
    return initial_state("build me a plan", USER_ID) | {
        "profile": profile,
        "profile_draft": draft,
    }


def _config(thread: str) -> dict:
    return {"configurable": {"thread_id": thread}}


async def _form(graph, config: dict, state: GraphState) -> dict[str, Any]:
    """Run until the form is shown, and return the payload the caller receives."""
    result = await graph.ainvoke(state, config)
    return result["__interrupt__"][0].value


# --- The form the user is shown ------------------------------------------------------------


async def test_the_run_suspends_on_a_form_rather_than_asking_in_prose(graph) -> None:
    """The reason this node exists: the caller gets fields it can render, not a
    sentence listing seven field names for the user to answer in free text."""
    payload = await _form(graph, _config("t1"), _start())

    assert payload["type"] == PROFILE_FORM_INTERRUPT
    assert [field["name"] for field in payload["fields"]] == list(COMPLETE)


async def test_the_form_arrives_pre_filled_with_what_the_user_already_said(
    graph,
) -> None:
    """A user who opened with their age and weight should not be asked to type them
    again — the draft read off their message is what the form starts from."""
    payload = await _form(
        graph, _config("t2"), _start(draft={"age": 27, "sex": "MALE"})
    )

    assert payload["values"] == {"age": 27, "sex": "MALE"}


async def test_nothing_is_asked_for_twice(graph) -> None:
    """Fields already on file are not on the form."""
    stored = {"age": 27, "sex": "MALE"}
    payload = await _form(graph, _config("t3"), _start(profile=stored))

    assert "age" not in [field["name"] for field in payload["fields"]]


# --- Submitting it -------------------------------------------------------------------------


async def test_a_complete_submission_is_saved_in_one_write(graph, saved) -> None:
    """The whole ask: the profile is written once, not once per field."""
    config = _config("t4")
    await _form(graph, config, _start())

    result = await graph.ainvoke(Command(resume=COMPLETE), config)

    assert len(saved) == 1
    assert saved[0]["age"] == 27
    assert saved[0]["training_days_per_week"] == 4
    assert result["profile"]["sex"] == "MALE"
    assert result["messages"][-1].content == PROFILE_SAVED_MESSAGE
    assert result["profile_status"] == "ready"
    assert result["user_outcome"] == "answered"


async def test_an_incomplete_submission_is_asked_again_and_nothing_is_saved(
    graph, saved
) -> None:
    """Every required field is verified before the write, so a half-filled form
    re-opens rather than storing a profile the coach cannot plan from."""
    config = _config("t5")
    await _form(graph, config, _start())

    result = await graph.ainvoke(Command(resume={"age": 27}), config)
    payload = result["__interrupt__"][0].value

    assert saved == []
    assert "sex" in payload["errors"]


async def test_a_re_asked_form_keeps_what_was_already_filled_in(graph, saved) -> None:
    """Being told one field is wrong must not cost the user the six they got right."""
    config = _config("t6")
    await _form(graph, config, _start())

    result = await graph.ainvoke(
        Command(resume={**COMPLETE, "training_days_per_week": 9}), config
    )
    payload = result["__interrupt__"][0].value

    assert "training_days_per_week" in payload["errors"]
    assert payload["values"]["age"] == 27


async def test_a_correction_after_a_rejected_submission_saves(graph, saved) -> None:
    """The loop has to end on the user's terms: a second, valid submission goes
    through rather than the form re-opening forever."""
    config = _config("t7")
    await _form(graph, config, _start())
    await graph.ainvoke(Command(resume={**COMPLETE, "age": 5}), config)

    result = await graph.ainvoke(Command(resume=COMPLETE), config)

    assert len(saved) == 1
    assert result["profile"]["age"] == 27


async def test_an_out_of_range_value_never_reaches_storage(graph, saved) -> None:
    """Present-but-invalid is caught by the same gate as absent."""
    config = _config("t8")
    await _form(graph, config, _start())

    result = await graph.ainvoke(Command(resume={**COMPLETE, "age": 5}), config)

    assert saved == []
    assert "age" in result["__interrupt__"][0].value["errors"]
