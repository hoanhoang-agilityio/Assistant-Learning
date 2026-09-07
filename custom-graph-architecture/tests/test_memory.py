"""Tests for the long-term memory service: what the store holds, and what separates it."""

import pytest

import src.services.memory as memory_service
from src.runtime import MemoryScope, namespace_for, plan_namespace
from src.runtime.backends.memory import InMemoryRuntime
from src.services.memory import (
    CURRENT_PLAN_KEY,
    delete,
    recall,
    recall_plan,
    save,
    save_plan,
)
from src.services.profile import PROFILE_KEY, load_profile, save_profile

USER_ID = "user-1"

PROFILE = {"age": 34, "goal": "FAT_LOSS"}


@pytest.fixture
async def store(monkeypatch: pytest.MonkeyPatch):
    """Point the memory service at an in-process store instead of Postgres."""
    runtime = InMemoryRuntime()
    monkeypatch.setattr(memory_service, "graph_runtime", runtime)
    yield await runtime.store()
    await runtime.close()


# --- One entry ----------------------------------------------------------------------------


async def test_an_entry_is_read_back_as_it_was_written(store) -> None:
    """The round trip every other test assumes."""
    await save(USER_ID, MemoryScope.FACTS, PROFILE_KEY, PROFILE)

    assert await recall(USER_ID, MemoryScope.FACTS, PROFILE_KEY) == PROFILE


async def test_an_absent_entry_reads_as_none(store) -> None:
    """A first-time user must not be a KeyError on the read path."""
    assert await recall(USER_ID, MemoryScope.FACTS, PROFILE_KEY) is None


async def test_a_second_write_merges_rather_than_replaces(store) -> None:
    """Memory accumulates across conversations; a replace would drop what came before."""
    await save(USER_ID, MemoryScope.FACTS, PROFILE_KEY, {"age": 34})
    await save(USER_ID, MemoryScope.FACTS, PROFILE_KEY, {"goal": "FAT_LOSS"})

    assert await recall(USER_ID, MemoryScope.FACTS, PROFILE_KEY) == PROFILE


async def test_a_restated_value_overwrites_the_old_one(store) -> None:
    """A user who changes their mind must not keep both answers."""
    await save(USER_ID, MemoryScope.FACTS, PROFILE_KEY, {"age": 34})
    await save(USER_ID, MemoryScope.FACTS, PROFILE_KEY, {"age": 35})

    assert (await recall(USER_ID, MemoryScope.FACTS, PROFILE_KEY))["age"] == 35


async def test_a_forgotten_entry_is_gone(store) -> None:
    """The user asked for it to be dropped, so a later read must not resurrect it."""
    await save(USER_ID, MemoryScope.FACTS, PROFILE_KEY, PROFILE)
    await delete(USER_ID, MemoryScope.FACTS, PROFILE_KEY)

    assert await recall(USER_ID, MemoryScope.FACTS, PROFILE_KEY) is None


# --- One user -----------------------------------------------------------------------------


async def test_one_users_memory_is_not_visible_to_another(store) -> None:
    """The namespace is the isolation boundary, and memory outlives the conversation."""
    await save(USER_ID, MemoryScope.FACTS, PROFILE_KEY, PROFILE)

    assert await recall("user-2", MemoryScope.FACTS, PROFILE_KEY) is None


async def test_an_anonymous_write_is_rejected(store) -> None:
    """Without a user id every caller's memory would pool into one namespace."""
    with pytest.raises(ValueError, match="user_id is required"):
        await save("", MemoryScope.FACTS, PROFILE_KEY, PROFILE)


# --- What the profile writes -------------------------------------------------------------


async def test_the_facts_scope_is_where_the_profile_lives(store) -> None:
    """Facts are the one scope with a writer, and the profile service goes through here."""
    await save_profile(USER_ID, {"age": 34})

    assert await recall(USER_ID, MemoryScope.FACTS, PROFILE_KEY) == {"age": 34}
    assert await load_profile(USER_ID) == {"age": 34}
    assert (
        await store.aget(namespace_for(USER_ID, MemoryScope.FACTS), PROFILE_KEY)
    ).value == {"age": 34}


async def test_the_profile_and_the_plan_do_not_share_a_namespace(store) -> None:
    """Both hang off the same user, and a collision would have one overwrite the other."""
    await save_profile(USER_ID, PROFILE)
    await save_plan(USER_ID, {"template_id": "tpl-1"})

    assert await load_profile(USER_ID) == PROFILE
    assert await recall_plan(USER_ID) == {"template_id": "tpl-1"}
    assert await recall(USER_ID, MemoryScope.FACTS, CURRENT_PLAN_KEY) is None
    assert await store.aget(plan_namespace(USER_ID), PROFILE_KEY) is None
