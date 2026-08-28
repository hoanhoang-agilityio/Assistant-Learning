"""Reading one turn for what the user would rather, and keeping it across conversations.

The scope ``recall_memory`` reads had no writer at all: the store, the accessors and the
tool were all built, and nothing ever put anything in. These are the tests for the half
that was missing.
"""

import pytest

import src.services.memory as memory_service
from src.runtime import MemoryScope
from src.runtime.backends.memory import InMemoryRuntime
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
    """ "I also hate lunges" adds to what they have already said."""
    merged = merge_entry({"disliked": ["burpees"]}, {"disliked": ["lunges"]})

    assert merged == {"disliked": ["burpees", "lunges"]}


def test_a_restated_scalar_replaces() -> None:
    """ "Actually, make it evenings" corrects what they said, it does not add to it."""
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
