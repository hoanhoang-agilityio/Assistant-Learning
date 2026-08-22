"""Tests for the ``load_context`` node and the profile/plan reads behind it."""

import pytest

import src.core.langgraph.nodes.context as context_node
import src.services.profile as profile_service
from src.core.langgraph.nodes.context import load_context, route_after_context
from src.core.langgraph.runtime import MemoryScope, namespace_for, plan_namespace
from src.core.langgraph.runtime.backends.memory import InMemoryRuntime
from src.schemas import initial_state
from src.services.profile import (
    CURRENT_PLAN_KEY,
    PROFILE_KEY,
    REQUIRED_PROFILE_FIELDS,
    UserContext,
    load_current_plan,
    load_profile,
    load_user_context,
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
    monkeypatch.setattr(profile_service, "graph_runtime", runtime)
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
    assert UserContext(profile=COMPLETE_PROFILE).is_complete


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
    """``request_missing_info`` asks in this order, so it must not vary between runs."""
    sparse = {"height_cm": 178.0}
    assert missing_profile_fields(sparse) == [
        name for name in REQUIRED_PROFILE_FIELDS if name != "height_cm"
    ]


# --- Store reads -------------------------------------------------------------------------


async def test_profile_and_plan_are_read_from_long_term_memory(store) -> None:
    """Both live outside the checkpointer, so a brand-new thread still finds them."""
    await _seed(store, profile=COMPLETE_PROFILE, plan=PLAN)

    context = await load_user_context(USER_ID)

    assert context == UserContext(profile=COMPLETE_PROFILE, plan=PLAN)


async def test_unknown_user_loads_an_empty_context(store) -> None:
    """A user with nothing stored yields no profile and no plan, not an error."""
    assert await load_user_context("nobody") == UserContext(profile=None, plan=None)


async def test_a_user_with_a_profile_but_no_plan_is_complete(store) -> None:
    """The plan is what the coaching branch produces; its absence is not missing context."""
    await _seed(store, profile=COMPLETE_PROFILE)

    context = await load_user_context(USER_ID)

    assert context.plan is None
    assert context.is_complete


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

    assert await load_user_context("user-2") == UserContext()


@pytest.mark.parametrize(
    "load",
    [load_profile, load_current_plan, load_user_context],
    ids=lambda f: f.__name__,
)
async def test_an_empty_user_id_is_rejected(store, load) -> None:
    """An anonymous read would address a namespace every anonymous caller shares."""
    with pytest.raises(ValueError, match="user_id is required"):
        await load("")


# --- The node ----------------------------------------------------------------------------


async def test_node_writes_profile_plan_and_completeness(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The node reports what it loaded plus the single routing bit the edges read."""

    async def loaded(user_id: str) -> UserContext:
        assert user_id == USER_ID
        return UserContext(profile=COMPLETE_PROFILE, plan=PLAN)

    monkeypatch.setattr(context_node, "load_user_context", loaded)

    actual_update = await load_context(initial_state("adjust my plan", USER_ID))

    assert actual_update == {
        "profile": COMPLETE_PROFILE,
        "plan": PLAN,
        "context_complete": True,
    }


async def test_node_marks_an_incomplete_profile(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A partial profile is loaded but must not be treated as ready to plan from."""

    async def loaded(_: str) -> UserContext:
        return UserContext(profile={"age": 34}, plan=None)

    monkeypatch.setattr(context_node, "load_user_context", loaded)

    actual_update = await load_context(initial_state("build me a plan", USER_ID))

    assert actual_update["profile"] == {"age": 34}
    assert actual_update["context_complete"] is False


async def test_node_reads_the_store_through_the_service(store) -> None:
    """End to end against a real store: seeded data reaches state unchanged."""
    await _seed(store, profile=COMPLETE_PROFILE, plan=PLAN)

    actual_update = await load_context(initial_state("build me a plan", USER_ID))

    assert actual_update == {
        "profile": COMPLETE_PROFILE,
        "plan": PLAN,
        "context_complete": True,
    }


@pytest.mark.parametrize(
    ("context_complete", "expected"),
    [(True, "complete"), (False, "incomplete")],
)
def test_route_after_context_follows_the_completeness_flag(
    context_complete: bool, expected: str
) -> None:
    """Routing is a pure read of what ``load_context`` decided."""
    state = initial_state("build me a plan", USER_ID) | {
        "context_complete": context_complete
    }
    assert route_after_context(state) == expected


def test_route_after_context_defaults_to_collecting_data() -> None:
    """With the flag unset, collect data rather than plan from an unknown profile."""
    state = initial_state("build me a plan", USER_ID)
    del state["context_complete"]
    assert route_after_context(state) == "incomplete"
