"""Tests for the ``request_missing_info`` node."""

import pytest
from langchain_core.messages import AIMessage

from src.core.langgraph.nodes.request_missing_info import (
    FIELD_PROMPTS,
    REQUEST_INTRO,
    REQUEST_OUTRO,
    build_missing_info_request,
    request_missing_info,
)
from src.schemas import initial_state
from src.services.profile import REQUIRED_PROFILE_FIELDS
from tests.test_load_context import USER_ID


def _state(missing_fields: list[str]) -> dict:
    """A state as it stands after ``check_profile_complete`` named the gaps."""
    return initial_state("build me a plan", USER_ID) | {
        "missing_fields": missing_fields
    }


def test_every_required_field_has_something_to_ask_for() -> None:
    """A field added to the required set without a prompt would be asked for by key name."""
    assert set(REQUIRED_PROFILE_FIELDS) <= set(FIELD_PROMPTS)


def test_target_weight_has_a_prompt_even_though_it_is_optional() -> None:
    """A revision can flag it for re-asking, so it needs a phrasing beyond its key name."""
    assert "target_weight_kg" in FIELD_PROMPTS


def test_only_the_missing_fields_are_asked_for() -> None:
    """Asking for data the user already gave is the failure this node exists to avoid."""
    request = build_missing_info_request(["goal", "training_days_per_week"])

    assert FIELD_PROMPTS["goal"] in request
    assert FIELD_PROMPTS["training_days_per_week"] in request
    assert FIELD_PROMPTS["age"] not in request


def test_the_request_keeps_the_order_it_was_given() -> None:
    """``check_profile_complete`` fixes the ask order; formatting must not shuffle it."""
    request = build_missing_info_request(["goal", "age"])

    assert request.index(FIELD_PROMPTS["goal"]) < request.index(FIELD_PROMPTS["age"])


def test_each_field_is_its_own_bullet() -> None:
    """One line per field, so a reply can be matched back to what was asked."""
    request = build_missing_info_request(["age", "sex"])

    assert request.count("\n- ") == 2


def test_an_unknown_field_still_appears_by_name() -> None:
    """A prompt missing from the map degrades to the field name, not to a silent drop."""
    assert "- bodyfat_pct" in build_missing_info_request(["bodyfat_pct"])


def test_an_empty_list_asks_for_the_whole_required_set() -> None:
    """Not knowing what is missing is the same position as knowing nothing about the user."""
    request = build_missing_info_request([])

    assert all(FIELD_PROMPTS[name] in request for name in REQUIRED_PROFILE_FIELDS)


@pytest.mark.parametrize("missing_fields", [["age"], []])
def test_the_request_is_framed_for_the_user(missing_fields: list[str]) -> None:
    """The user is told why they are being asked and that one reply is enough."""
    request = build_missing_info_request(missing_fields)

    assert request.startswith(REQUEST_INTRO)
    assert request.endswith(REQUEST_OUTRO)


async def test_the_node_returns_the_request_as_output_and_transcript() -> None:
    """The suspended turn shows the question, and the conversation records having asked."""
    actual_update = await request_missing_info(_state(["age", "goal"]))

    expected = build_missing_info_request(["age", "goal"])
    assert actual_update["final_message"] == expected
    assert [message.content for message in actual_update["messages"]] == [expected]
    assert isinstance(actual_update["messages"][0], AIMessage)


async def test_the_node_survives_a_state_with_no_missing_fields_key() -> None:
    """Reached out of order, it asks rather than raising mid-run."""
    state = initial_state("build me a plan", USER_ID)
    del state["missing_fields"]

    actual_update = await request_missing_info(state)

    assert actual_update["final_message"] == build_missing_info_request([])


@pytest.mark.parametrize(("asked_before", "expected"), [(0, 1), (1, 2), (2, 3)])
async def test_each_question_spends_one_attempt(
    asked_before: int, expected: int
) -> None:
    """The limit counts questions put to the user, not replies received."""
    state = _state(["age"]) | {"user_info_retry_count": asked_before}

    actual_update = await request_missing_info(state)

    assert actual_update["user_info_retry_count"] == expected


async def test_a_state_with_no_counter_starts_it_at_one() -> None:
    """A run checkpointed before the counter existed still records this question."""
    state = _state(["age"])
    del state["user_info_retry_count"]

    actual_update = await request_missing_info(state)

    assert actual_update["user_info_retry_count"] == 1
