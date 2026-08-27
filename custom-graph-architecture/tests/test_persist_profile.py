"""Tests for ``save_profile`` and the ``persist_profile`` node that calls it."""

from src.core.langgraph.nodes.persist_profile import persist_profile
from src.schemas import initial_state
from src.services.profile import load_profile, save_profile
from tests.test_load_user_context import COMPLETE_PROFILE, USER_ID, store  # noqa: F401

# --- ``save_profile``: the write the node performs ---------------------


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


# --- The node -------------------------------------------------------------------------


async def test_the_node_persists_the_runtime_profile(store) -> None:  # noqa: F811
    """The write has landed by the time the node returns, so a reload cannot miss it."""
    state = initial_state("build me a plan", USER_ID) | {"profile": COMPLETE_PROFILE}

    actual_update = await persist_profile(state)

    assert actual_update == {}
    assert await load_profile(USER_ID) == COMPLETE_PROFILE


async def test_the_node_does_nothing_with_no_profile(store) -> None:  # noqa: F811
    """Reached with an empty profile, there is nothing worth persisting."""
    state = initial_state("build me a plan", USER_ID) | {"profile": None}

    await persist_profile(state)

    assert await load_profile(USER_ID) is None
