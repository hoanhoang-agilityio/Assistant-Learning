"""Tests for the ``user_info_exhausted`` node."""

from langchain_core.messages import AIMessage

from src.core.langgraph.nodes.request_missing_info import FIELD_PROMPTS
from src.core.langgraph.nodes.user_info_exhausted import (
    EXHAUSTED_INTRO,
    EXHAUSTED_OUTRO,
    build_exhausted_message,
    user_info_exhausted,
)
from src.schemas import initial_state
from tests.test_load_context import USER_ID


def _state(missing_fields: list[str]) -> dict:
    """A state as it stands after the user was asked too many times."""
    return initial_state("build me a plan", USER_ID) | {
        "missing_fields": missing_fields,
        "user_info_retry_count": 3,
    }


def test_the_user_is_told_no_plan_was_built() -> None:
    """Stopping silently would read as a plan that simply never arrived."""
    message = build_exhausted_message(["goal"])

    assert message.startswith(EXHAUSTED_INTRO)
    assert message.endswith(EXHAUSTED_OUTRO)


def test_the_outstanding_fields_are_named_one_last_time() -> None:
    """The user can only act on the refusal if they know what was still needed."""
    message = build_exhausted_message(["goal", "age"])

    assert FIELD_PROMPTS["goal"] in message
    assert FIELD_PROMPTS["age"] in message


def test_fields_already_supplied_are_not_listed() -> None:
    """Listing answered fields would make the refusal look wrong to the user."""
    assert FIELD_PROMPTS["sex"] not in build_exhausted_message(["goal"])


def test_no_named_fields_still_produces_a_readable_refusal() -> None:
    """With nothing to list, the message must not trail off into an empty section."""
    message = build_exhausted_message([])

    assert message == f"{EXHAUSTED_INTRO}\n\n{EXHAUSTED_OUTRO}"


async def test_the_node_ends_the_run_with_the_refusal() -> None:
    """A terminal node, so what it writes is what the caller shows."""
    actual_update = await user_info_exhausted(_state(["goal"]))

    expected = build_exhausted_message(["goal"])
    assert actual_update["final_message"] == expected
    assert [message.content for message in actual_update["messages"]] == [expected]
    assert isinstance(actual_update["messages"][0], AIMessage)
