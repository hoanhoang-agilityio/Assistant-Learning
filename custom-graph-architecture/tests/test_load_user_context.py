"""Tests for the profile/plan reads long-term memory backs."""

import pytest

import src.services.memory as memory_service
from src.runtime import MemoryScope, namespace_for, plan_namespace
from src.runtime.backends.memory import InMemoryRuntime
from src.services.memory import CURRENT_PLAN_KEY
from src.services.profile import (
    PROFILE_KEY,
    REQUIRED_PROFILE_FIELDS,
    load_current_plan,
    load_profile,
    missing_profile_fields,
)

USER_ID = "user-1"

COMPLETE_PROFILE: dict = {
    "age": 34,
    "sex": "MALE",
    "height_cm": 178.0,
    "current_weight_kg": 82.5,
    "activity_level": "MODERATE",
    "goal": "FAT_LOSS",
    "training_days_per_week": 4,
}

PLAN: dict = {"id": "plan-7", "training_days": [{"day_number": 1, "name": "Upper"}]}


@pytest.fixture
async def store(monkeypatch: pytest.MonkeyPatch):
    """Point the profile service at an in-process store instead of Postgres."""
    runtime = InMemoryRuntime()
    monkeypatch.setattr(memory_service, "graph_runtime", runtime)
    yield await runtime.store()
    await runtime.close()


async def _seed(
    store, *, profile: dict | None = None, plan: dict | None = None
) -> None:
    """Write a profile and/or plan into the long-term store for one user."""
    if profile is not None:
        await store.aput(
            namespace_for(USER_ID, MemoryScope.FACTS), PROFILE_KEY, profile
        )
    if plan is not None:
        await store.aput(plan_namespace(USER_ID), CURRENT_PLAN_KEY, plan)


# --- Completeness rules ------------------------------------------------------------------


def test_no_profile_means_every_required_field_is_missing() -> None:
    """A first-time user must be asked for the whole required set, not for nothing."""
    assert missing_profile_fields(None) == list(REQUIRED_PROFILE_FIELDS)
    assert missing_profile_fields({}) == list(REQUIRED_PROFILE_FIELDS)


def test_complete_profile_has_no_missing_fields() -> None:
    """Every field the coach agent needs is present, so the graph may start planning."""
    assert missing_profile_fields(COMPLETE_PROFILE) == []


def test_optional_fields_are_not_required() -> None:
    """Injuries, equipment and preferences all have safe defaults — never interrupt for them."""
    assert missing_profile_fields(COMPLETE_PROFILE | {"injuries": None}) == []


@pytest.mark.parametrize("blank", [None, "", "   "])
def test_absent_and_blank_values_both_count_as_missing(blank: object) -> None:
    """A field stored as an empty string is an unanswered question, not an answer."""
    assert missing_profile_fields(COMPLETE_PROFILE | {"goal": blank}) == ["goal"]


def test_zero_is_a_value_and_not_a_missing_field() -> None:
    """Presence is checked explicitly, so a falsy-but-real number is not re-requested."""
    assert (
        missing_profile_fields(COMPLETE_PROFILE | {"training_days_per_week": 0}) == []
    )


def test_missing_fields_keep_the_declared_ask_order() -> None:
    """``request_missing_profile_fields`` asks in this order, so it must not vary between runs."""
    sparse = {"height_cm": 178.0}
    assert missing_profile_fields(sparse) == [
        name for name in REQUIRED_PROFILE_FIELDS if name != "height_cm"
    ]


# --- Store reads -------------------------------------------------------------------------


async def test_profile_and_plan_are_read_from_long_term_memory(store) -> None:
    """Both live outside the checkpointer, so a brand-new thread still finds them."""
    await _seed(store, profile=COMPLETE_PROFILE, plan=PLAN)

    assert await load_profile(USER_ID) == COMPLETE_PROFILE
    assert await load_current_plan(USER_ID) == PLAN


async def test_unknown_user_has_no_profile_or_plan(store) -> None:
    """A user with nothing stored yields no profile and no plan, not an error."""
    assert await load_profile("nobody") is None
    assert await load_current_plan("nobody") is None


async def test_a_user_with_a_profile_but_no_plan_is_still_complete(store) -> None:
    """The plan is what the coaching branch produces; its absence is not missing context."""
    await _seed(store, profile=COMPLETE_PROFILE)

    assert await load_current_plan(USER_ID) is None
    assert missing_profile_fields(await load_profile(USER_ID)) == []


async def test_loaded_values_are_copies_of_what_the_store_holds(store) -> None:
    """State must not alias long-term memory, or a state update would rewrite the store."""
    await _seed(store, profile=COMPLETE_PROFILE, plan=PLAN)

    profile = await load_profile(USER_ID)
    plan = await load_current_plan(USER_ID)
    profile["goal"] = "MUSCLE_GAIN"
    plan["id"] = "tampered"

    assert (await load_profile(USER_ID))["goal"] == "FAT_LOSS"
    assert (await load_current_plan(USER_ID))["id"] == "plan-7"


async def test_one_users_context_is_never_read_for_another(store) -> None:
    """Namespacing is the isolation boundary; a leak here would plan against a stranger."""
    await _seed(store, profile=COMPLETE_PROFILE, plan=PLAN)

    assert await load_profile("user-2") is None
    assert await load_current_plan("user-2") is None


@pytest.mark.parametrize(
    "load",
    [load_profile, load_current_plan],
    ids=lambda f: f.__name__,
)
async def test_an_empty_user_id_is_rejected(store, load) -> None:
    """An anonymous read would address a namespace every anonymous caller shares."""
    with pytest.raises(ValueError, match="user_id is required"):
        await load("")
