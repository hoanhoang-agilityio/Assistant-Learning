"""Tests for the long-term memory service: the three scopes and what separates them."""

import pytest

import src.services.memory as memory_service
from src.runtime import MemoryScope, namespace_for
from src.runtime.backends.memory import InMemoryRuntime
from src.services.memory import (
    MAX_ENTRIES_PER_SCOPE,
    UserMemory,
    delete,
    load_user_memory,
    recall,
    recall_scope,
    save,
)
from src.services.profile import PROFILE_KEY, load_profile, save_profile

USER_ID = "user-1"

FOUR_DAY_SPLIT = {"days_per_week": 4, "stated_on": "2026-08-20"}
SKIPS_LONG_SESSIONS = {"pattern": "skips sessions over 60 minutes", "observations": 3}


@pytest.fixture
async def store(monkeypatch: pytest.MonkeyPatch):
    """Point the memory service at an in-process store instead of Postgres."""
    runtime = InMemoryRuntime()
    monkeypatch.setattr(memory_service, "graph_runtime", runtime)
    yield await runtime.store()
    await runtime.close()


# --- One entry ----------------------------------------------------------------------------


async def test_an_entry_is_read_back_as_it_was_written(store) -> None:
    """The round trip the other tests assume, on the scope that had no writer before."""
    await save(USER_ID, MemoryScope.PREFERENCES, "schedule", FOUR_DAY_SPLIT)

    assert await recall(USER_ID, MemoryScope.PREFERENCES, "schedule") == FOUR_DAY_SPLIT


async def test_an_absent_entry_reads_as_none(store) -> None:
    """A first-time user must not be a KeyError on the read path."""
    assert await recall(USER_ID, MemoryScope.KNOWLEDGE, "adherence") is None


async def test_a_second_write_merges_rather_than_replaces(store) -> None:
    """Memory accumulates across conversations; a replace would drop what came before."""
    await save(USER_ID, MemoryScope.PREFERENCES, "schedule", {"days_per_week": 4})
    await save(USER_ID, MemoryScope.PREFERENCES, "schedule", {"time": "morning"})

    assert await recall(USER_ID, MemoryScope.PREFERENCES, "schedule") == {
        "days_per_week": 4,
        "time": "morning",
    }


async def test_a_restated_value_overwrites_the_old_one(store) -> None:
    """A user who changes their mind must not keep both answers."""
    await save(USER_ID, MemoryScope.PREFERENCES, "schedule", {"days_per_week": 4})
    await save(USER_ID, MemoryScope.PREFERENCES, "schedule", {"days_per_week": 3})

    assert (await recall(USER_ID, MemoryScope.PREFERENCES, "schedule"))[
        "days_per_week"
    ] == 3


async def test_a_forgotten_entry_is_gone(store) -> None:
    """The user asked for it to be dropped, so a later read must not resurrect it."""
    await save(USER_ID, MemoryScope.PREFERENCES, "schedule", FOUR_DAY_SPLIT)
    await delete(USER_ID, MemoryScope.PREFERENCES, "schedule")

    assert await recall(USER_ID, MemoryScope.PREFERENCES, "schedule") is None


# --- One scope ----------------------------------------------------------------------------


async def test_a_scope_reads_back_every_entry_in_it(store) -> None:
    """The agent is handed the whole scope, not one key it would have to guess."""
    await save(USER_ID, MemoryScope.PREFERENCES, "schedule", FOUR_DAY_SPLIT)
    await save(USER_ID, MemoryScope.PREFERENCES, "diet", {"style": "vegetarian"})

    assert await recall_scope(USER_ID, MemoryScope.PREFERENCES) == {
        "schedule": FOUR_DAY_SPLIT,
        "diet": {"style": "vegetarian"},
    }


async def test_an_empty_scope_reads_as_an_empty_mapping(store) -> None:
    """Callers branch on emptiness, so None here would be a second thing to check."""
    assert await recall_scope(USER_ID, MemoryScope.KNOWLEDGE) == {}


async def test_a_scope_read_does_not_reach_into_another(store) -> None:
    """Preferences are what the user asked for; knowledge is what was inferred."""
    await save(USER_ID, MemoryScope.PREFERENCES, "schedule", FOUR_DAY_SPLIT)
    await save(USER_ID, MemoryScope.KNOWLEDGE, "adherence", SKIPS_LONG_SESSIONS)

    assert set(await recall_scope(USER_ID, MemoryScope.PREFERENCES)) == {"schedule"}
    assert set(await recall_scope(USER_ID, MemoryScope.KNOWLEDGE)) == {"adherence"}


async def test_the_same_key_in_two_scopes_is_two_entries(store) -> None:
    """A stated preference and an observed pattern can disagree and both must survive."""
    await save(USER_ID, MemoryScope.PREFERENCES, "days", {"source": "stated"})
    await save(USER_ID, MemoryScope.KNOWLEDGE, "days", {"source": "observed"})

    assert await recall(USER_ID, MemoryScope.PREFERENCES, "days") == {
        "source": "stated"
    }
    assert await recall(USER_ID, MemoryScope.KNOWLEDGE, "days") == {
        "source": "observed"
    }


async def test_a_scope_read_is_bounded(store) -> None:
    """An unbounded read would put a runaway writer's whole history in the prompt."""
    for index in range(MAX_ENTRIES_PER_SCOPE + 10):
        await save(USER_ID, MemoryScope.KNOWLEDGE, f"note-{index}", {"i": index})

    assert len(await recall_scope(USER_ID, MemoryScope.KNOWLEDGE)) == (
        MAX_ENTRIES_PER_SCOPE
    )


# --- One user -----------------------------------------------------------------------------


async def test_one_users_memory_is_not_visible_to_another(store) -> None:
    """The namespace is the isolation boundary, and memory outlives the conversation."""
    await save(USER_ID, MemoryScope.PREFERENCES, "schedule", FOUR_DAY_SPLIT)

    assert await recall("user-2", MemoryScope.PREFERENCES, "schedule") is None
    assert await recall_scope("user-2", MemoryScope.PREFERENCES) == {}


async def test_an_anonymous_write_is_rejected(store) -> None:
    """Without a user id every caller's memory would pool into one namespace."""
    with pytest.raises(ValueError, match="user_id is required"):
        await save("", MemoryScope.PREFERENCES, "schedule", FOUR_DAY_SPLIT)


# --- What the agent is handed -------------------------------------------------------------


async def test_both_scopes_are_loaded_together(store) -> None:
    """One await for the whole memory, so a tool call is one round trip rather than two."""
    await save(USER_ID, MemoryScope.PREFERENCES, "schedule", FOUR_DAY_SPLIT)
    await save(USER_ID, MemoryScope.KNOWLEDGE, "adherence", SKIPS_LONG_SESSIONS)

    assert await load_user_memory(USER_ID) == UserMemory(
        preferences={"schedule": FOUR_DAY_SPLIT},
        knowledge={"adherence": SKIPS_LONG_SESSIONS},
    )


async def test_a_first_time_user_has_empty_memory(store) -> None:
    """Nothing recorded is the normal case on the first conversation, not a failure."""
    memory = await load_user_memory(USER_ID)

    assert memory == UserMemory(preferences={}, knowledge={})
    assert memory.is_empty


async def test_memory_is_not_empty_once_either_scope_has_an_entry(store) -> None:
    """A user with only observed patterns still has something worth telling the coach."""
    await save(USER_ID, MemoryScope.KNOWLEDGE, "adherence", SKIPS_LONG_SESSIONS)

    assert not (await load_user_memory(USER_ID)).is_empty


async def test_the_facts_scope_is_where_the_profile_already_lives(store) -> None:
    """Facts are the third scope, and the profile service writes them through this layer."""
    await save_profile(USER_ID, {"age": 34})

    assert await recall(USER_ID, MemoryScope.FACTS, PROFILE_KEY) == {"age": 34}
    assert await load_profile(USER_ID) == {"age": 34}
    assert (
        await store.aget(namespace_for(USER_ID, MemoryScope.FACTS), PROFILE_KEY)
    ).value == {"age": 34}


async def test_the_profile_is_not_visible_in_the_other_two_scopes(store) -> None:
    """Facts the coach requires must not be confused with preferences it may override."""
    await save_profile(USER_ID, {"age": 34})

    assert (await load_user_memory(USER_ID)).is_empty
