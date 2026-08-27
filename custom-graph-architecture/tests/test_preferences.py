"""Reading one turn for what the user would rather, and keeping it across conversations.

The scope ``recall_memory`` reads had no writer at all: the store, the accessors and the
tool were all built, and nothing ever put anything in. These are the tests for the half
that was missing.
"""

import pytest

import src.services.memory as memory_service
from src.core.langgraph.nodes.persist_preferences import persist_preferences
from src.core.langgraph.runtime import MemoryScope
from src.core.langgraph.runtime.backends.memory import InMemoryRuntime
from src.schemas import GraphState
from src.services.memory import recall
from src.services.preferences import (
    EXERCISES_KEY,
    SCHEDULE_KEY,
    load_preferences,
    merge_entry,
    save_preferences,
    stated_preferences,
)
from src.services.turn import PreferenceStatement

USER_ID = "user-prefs"


@pytest.fixture
async def store(monkeypatch: pytest.MonkeyPatch):
    """Point the memory service at an in-process store instead of Postgres."""
    runtime = InMemoryRuntime()
    monkeypatch.setattr(memory_service, "graph_runtime", runtime)
    yield await runtime.store()
    await runtime.close()


def _state(**extracted: object) -> GraphState:
    """A run's state carrying what ``parse_turn`` read from this turn."""
    return GraphState(
        messages=[], user_query="", user_id=USER_ID, extracted_facts=extracted or None
    )


# --- Reading one turn ----------------------------------------------------------------


def test_a_turn_that_states_nothing_asks_for_no_write() -> None:
    """The usual case. A turn about anything else must not touch the store."""
    assert stated_preferences(PreferenceStatement()) == {}
    assert PreferenceStatement().is_empty


def test_each_kind_lands_in_its_own_entry() -> None:
    """One entry per kind, so a turn about food does not rewrite one about scheduling."""
    entries = stated_preferences(
        PreferenceStatement(schedule="mornings", disliked_exercises=["Burpees"])
    )

    assert entries == {
        SCHEDULE_KEY: {"preferred": "mornings"},
        EXERCISES_KEY: {"disliked": ["burpees"]},
    }


def test_stated_exercises_are_normalised() -> None:
    """The same movement typed three ways is one dislike, not three."""
    entries = stated_preferences(
        PreferenceStatement(disliked_exercises=["Burpees", " burpees ", "", "lunges"])
    )

    assert entries[EXERCISES_KEY] == {"disliked": ["burpees", "lunges"]}


# --- Merging with what they said before ----------------------------------------------


def test_a_further_dislike_is_added_rather_than_replacing() -> None:
    """"I also hate lunges" adds to what they have already said."""
    merged = merge_entry({"disliked": ["burpees"]}, {"disliked": ["lunges"]})

    assert merged == {"disliked": ["burpees", "lunges"]}


def test_a_restated_scalar_replaces() -> None:
    """"Actually, make it evenings" corrects what they said, it does not add to it."""
    merged = merge_entry({"preferred": "mornings"}, {"preferred": "evenings"})

    assert merged == {"preferred": "evenings"}


def test_an_unmentioned_field_survives_the_merge() -> None:
    """A turn about dislikes must not wipe out the likes recorded beside them."""
    merged = merge_entry({"liked": ["squats"]}, {"disliked": ["burpees"]})

    assert merged == {"liked": ["squats"], "disliked": ["burpees"]}


# --- Through the store ---------------------------------------------------------------


async def test_a_preference_outlives_the_conversation_it_was_stated_in(store) -> None:
    """Keyed by user, not by thread: that is what makes a new chat still know it."""
    await save_preferences(USER_ID, PreferenceStatement(schedule="mornings"))

    assert await load_preferences(USER_ID) == {SCHEDULE_KEY: {"preferred": "mornings"}}


async def test_two_turns_accumulate(store) -> None:
    """The second conversation adds to the first rather than starting the record again."""
    await save_preferences(USER_ID, PreferenceStatement(disliked_exercises=["burpees"]))
    await save_preferences(USER_ID, PreferenceStatement(disliked_exercises=["lunges"]))

    assert await recall(USER_ID, MemoryScope.PREFERENCES, EXERCISES_KEY) == {
        "disliked": ["burpees", "lunges"]
    }


# --- The node ------------------------------------------------------------------------


async def test_the_node_writes_what_the_turn_stated(store) -> None:
    """``parse_turn`` reads it in the same call as the profile; this is what stores it."""
    await persist_preferences(_state(preferences={"schedule": "mornings"}))

    assert await load_preferences(USER_ID) == {SCHEDULE_KEY: {"preferred": "mornings"}}


async def test_the_node_writes_nothing_for_a_turn_that_stated_nothing(store) -> None:
    """Most turns state no preference, and each write is a round trip."""
    await persist_preferences(_state(age=27))

    assert await load_preferences(USER_ID) == {}


async def test_the_node_survives_a_turn_it_could_not_parse(store) -> None:
    """A failed parse leaves no facts at all; the node runs unconditionally regardless."""
    assert await persist_preferences(_state()) == {}
