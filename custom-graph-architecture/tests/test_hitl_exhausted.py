"""Tests for the ``hitl_exhausted`` node."""

from langchain_core.messages import AIMessage

from src.core.configs.config import settings
from src.core.langgraph.nodes.hitl_exhausted import (
    HITL_EXHAUSTED_MESSAGE,
    hitl_exhausted,
)
from src.schemas import initial_state
from tests.test_load_user_context import USER_ID

PLAN = {"goal": "fat_loss", "training_days_per_week": 4}


def _state() -> dict:
    """State as it stands after the revision budget ran out."""
    return initial_state("build me a plan", USER_ID) | {
        "plan": PLAN,
        "hitl_decision": "reject",
        "hitl_feedback": "still not right",
        "hitl_retry_count": settings.HITL_MAX_RETRIES,
    }


async def test_the_node_ends_the_run_with_the_refusal() -> None:
    """A terminal node, so what it writes is what the caller shows."""
    update = await hitl_exhausted(_state())

    assert update["final_message"] == HITL_EXHAUSTED_MESSAGE
    assert [message.content for message in update["messages"]] == [
        HITL_EXHAUSTED_MESSAGE
    ]
    assert isinstance(update["messages"][0], AIMessage)


async def test_the_unapproved_plan_is_left_alone() -> None:
    """The user's stored plan is still theirs; giving up must not disturb it."""
    update = await hitl_exhausted(_state())

    assert "plan" not in update
