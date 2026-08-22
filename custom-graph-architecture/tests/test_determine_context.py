"""Tests for the ``determine_context`` node."""

import pytest

import src.services.profile as profile_service
from src.core.langgraph.nodes.context import determine_context
from src.schemas import initial_state
from src.services.profile import REQUIRED_PROFILE_FIELDS
from tests.test_load_context import COMPLETE_PROFILE, USER_ID


def _state(profile: dict | None) -> dict:
    """A state as it stands after ``load_context`` routed the run here."""
    return initial_state("build me a plan", USER_ID) | {"profile": profile}


async def test_a_user_with_no_profile_is_asked_for_everything() -> None:
    """A first-time user needs the whole required set named, not an empty request."""
    actual_update = await determine_context(_state(None))

    assert actual_update == {"missing_fields": list(REQUIRED_PROFILE_FIELDS)}


async def test_only_the_absent_fields_are_named() -> None:
    """Data already stored must not be requested again."""
    partial = {name: COMPLETE_PROFILE[name] for name in ("age", "sex", "height_cm")}

    actual_update = await determine_context(_state(partial))

    assert actual_update == {
        "missing_fields": [
            "current_weight_kg",
            "activity_level",
            "goal",
            "training_days_per_week",
        ]
    }


@pytest.mark.parametrize("blank", [None, "", "   "])
async def test_a_blank_stored_value_is_still_missing(blank: object) -> None:
    """A field saved as an empty string is an unanswered question, not an answer."""
    actual_update = await determine_context(_state(COMPLETE_PROFILE | {"goal": blank}))

    assert actual_update == {"missing_fields": ["goal"]}


async def test_a_complete_profile_names_nothing() -> None:
    """Unreachable through ``load_context``'s routing, but it must not invent a request."""
    actual_update = await determine_context(_state(COMPLETE_PROFILE))

    assert actual_update == {"missing_fields": []}


async def test_the_node_reads_state_and_not_the_store(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """``load_context`` already paid for the read; a second one could disagree with it."""

    async def fail(*args: object, **kwargs: object) -> None:
        raise AssertionError("determine_context must not touch long-term memory")

    monkeypatch.setattr(profile_service.graph_runtime, "store", fail)

    assert await determine_context(_state({"age": 34})) == {
        "missing_fields": [
            "sex",
            "height_cm",
            "current_weight_kg",
            "activity_level",
            "goal",
            "training_days_per_week",
        ]
    }
