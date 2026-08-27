"""Tests for the ``hitl_rejected_no_feedback`` node."""

from langchain_core.messages import AIMessage

from src.core.langgraph.nodes.hitl_rejected_no_feedback import (
    HITL_REJECTED_NO_FEEDBACK_MESSAGE,
    hitl_rejected_no_feedback,
)
from src.schemas import initial_state
from tests.test_load_user_context import USER_ID

PLAN = {"goal": "fat_loss", "training_days_per_week": 4}


def _state() -> dict:
    """State as it stands after a rejection that carried no feedback."""
    return initial_state("build me a plan", USER_ID) | {
        "plan": PLAN,
        "hitl_decision": "reject",
        "hitl_feedback": None,
    }


async def test_the_node_ends_the_run_with_the_refusal() -> None:
    """A terminal node, so what it writes is what the caller shows."""
    update = await hitl_rejected_no_feedback(_state())

    assert update["final_message"] == HITL_REJECTED_NO_FEEDBACK_MESSAGE
    assert [message.content for message in update["messages"]] == [
        HITL_REJECTED_NO_FEEDBACK_MESSAGE
    ]
    assert isinstance(update["messages"][0], AIMessage)


async def test_the_rejected_plan_is_left_alone() -> None:
    """The user's stored plan is still theirs; a bare rejection must not disturb it."""
    update = await hitl_rejected_no_feedback(_state())

    assert "plan" not in update
