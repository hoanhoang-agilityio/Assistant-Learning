"""Tests for ``save_profile``, its background wrapper, and the ``bg_save_profile`` node."""

import asyncio

import pytest

from src.core.langgraph.nodes.bg_save_profile import bg_save_profile
from src.core.langgraph.runtime import MemoryScope, namespace_for
from src.schemas import initial_state
from src.services.profile import (
    PROFILE_KEY,
    flush_pending_saves,
    load_profile,
    save_profile,
    save_profile_in_background,
)
from tests.test_load_context import COMPLETE_PROFILE, USER_ID, store  # noqa: F401

# --- ``save_profile``: the persistence the background task wraps ---------------------


async def test_new_fields_are_persisted(store) -> None:  # noqa: F811
    """The point of the write: the profile outlives the thread it was given in."""
    await save_profile(USER_ID, {"age": 34, "goal": "FAT_LOSS"})

    assert await load_profile(USER_ID) == {"age": 34, "goal": "FAT_LOSS"}


async def test_a_second_answer_adds_to_the_first(store) -> None:  # noqa: F811
    """The loop collects across turns, so a save must merge rather than replace."""
    await save_profile(USER_ID, {"age": 34})
    await save_profile(USER_ID, {"goal": "FAT_LOSS"})

    assert await load_profile(USER_ID) == {"age": 34, "goal": "FAT_LOSS"}


async def test_a_correction_overwrites_the_stored_value(store) -> None:  # noqa: F811
    """A user who says they were wrong must end up with the corrected value."""
    await save_profile(USER_ID, {"current_weight_kg": 82.5})
    await save_profile(USER_ID, {"current_weight_kg": 80.0})

    assert (await load_profile(USER_ID))["current_weight_kg"] == 80.0


async def test_one_users_answer_is_not_written_to_another(store) -> None:  # noqa: F811
    """The namespace is the isolation boundary on writes as well as on reads."""
    await save_profile(USER_ID, {"age": 34})

    assert await load_profile("user-2") is None


# --- ``save_profile_in_background``: fire-and-forget persistence ---------------------


async def test_a_background_save_lands_once_flushed(store) -> None:  # noqa: F811
    """The whole point: the caller does not await the write, but it still happens."""
    save_profile_in_background(USER_ID, COMPLETE_PROFILE)

    await flush_pending_saves()

    assert await load_profile(USER_ID) == COMPLETE_PROFILE


async def test_a_background_save_does_not_block_the_caller(store) -> None:  # noqa: F811
    """Scheduling the task must return immediately, before the write completes."""
    task = save_profile_in_background(USER_ID, COMPLETE_PROFILE)

    assert not task.done()

    await flush_pending_saves()


async def test_flushing_with_nothing_pending_is_a_no_op() -> None:
    """A quiet run must not hang waiting on saves that were never scheduled."""
    await flush_pending_saves()


async def test_a_failed_background_save_is_logged_not_raised(
    store,  # noqa: F811
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """There is no caller left awaiting this task; a raised exception would go nowhere."""
    import src.services.profile as profile_service

    async def broken_save(*args: object, **kwargs: object) -> None:
        raise RuntimeError("store unavailable")

    monkeypatch.setattr(profile_service, "save_profile", broken_save)

    save_profile_in_background(USER_ID, COMPLETE_PROFILE)

    await flush_pending_saves()  # must not raise


async def test_two_background_saves_can_be_flushed_together(store) -> None:  # noqa: F811
    """A burst of turns must not leave earlier saves stranded in the registry."""
    save_profile_in_background(USER_ID, {"age": 34})
    save_profile_in_background("user-2", {"age": 40})

    await flush_pending_saves()

    assert (await load_profile(USER_ID))["age"] == 34
    assert (await load_profile("user-2"))["age"] == 40


# --- The node -------------------------------------------------------------------------


async def test_the_node_schedules_a_save_without_awaiting_it(
    store,  # noqa: F811
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """``coach_agent`` runs off the state the node returns, not off a completed write."""
    state = initial_state("build me a plan", USER_ID) | {"profile": COMPLETE_PROFILE}

    actual_update = await bg_save_profile(state)

    assert actual_update == {}
    await flush_pending_saves()
    assert await load_profile(USER_ID) == COMPLETE_PROFILE


async def test_the_node_does_nothing_with_no_profile(store) -> None:  # noqa: F811
    """Reached with an empty profile, there is nothing worth persisting."""
    state = initial_state("build me a plan", USER_ID) | {"profile": None}

    await bg_save_profile(state)
    await flush_pending_saves()

    assert await load_profile(USER_ID) is None
