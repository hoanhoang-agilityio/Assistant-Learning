"""Tests for the ``finalize_turn`` node: what it persists, and what the run ends on."""

from src.core.langgraph.nodes.finalize_turn import PLAN_SAVED_MESSAGE, finalize_turn
from src.schemas import initial_state
from src.services.memory import save_plan
from src.services.profile import load_current_plan
from tests.test_load_user_context import PLAN, USER_ID, store  # noqa: F401


def _state(**overrides: object) -> dict:
    """A state as it stands when a branch has finished producing whatever it produces."""
    return initial_state("build me a plan", USER_ID) | overrides


# --- The plan write --------------------------------------------------------------------


async def test_save_plan_round_trips_through_long_term_memory(store) -> None:  # noqa: F811
    """The plan outlives the thread it was approved on, or the next run replans from nothing."""
    await save_plan(USER_ID, PLAN)

    assert await load_current_plan(USER_ID) == PLAN


async def test_an_approved_plan_is_persisted(store) -> None:  # noqa: F811
    """Approval is the only signal that a plan is the user's; nothing else stores one."""
    await finalize_turn(_state(hitl_decision="approve", plan=PLAN))

    assert await load_current_plan(USER_ID) == PLAN


async def test_a_rejected_plan_is_not_persisted(store) -> None:  # noqa: F811
    """A plan the user turned down must not become the plan they are coached from."""
    await finalize_turn(_state(hitl_decision="reject", plan=PLAN))

    assert await load_current_plan(USER_ID) is None


async def test_a_turn_that_produced_no_plan_writes_nothing(store) -> None:  # noqa: F811
    """The QA branch and every refusal reach this node too."""
    await finalize_turn(_state(qa_answer="creatine is well studied."))

    assert await load_current_plan(USER_ID) is None


async def test_an_approval_with_no_plan_writes_nothing(store) -> None:  # noqa: F811
    """Reached out of order, the node must not write an empty plan over a real one."""
    await finalize_turn(_state(hitl_decision="approve", plan=None))

    assert await load_current_plan(USER_ID) is None


# --- The last word ---------------------------------------------------------------------


async def test_an_approval_ends_the_run_saying_so(store) -> None:  # noqa: F811
    """Approve was the one branch that used to end the run without a word to the user."""
    actual_update = await finalize_turn(_state(hitl_decision="approve", plan=PLAN))

    assert actual_update["final_message"] == PLAN_SAVED_MESSAGE
    assert [message.content for message in actual_update["messages"]] == [
        PLAN_SAVED_MESSAGE
    ]


async def test_a_faithful_answer_becomes_the_final_message(store) -> None:  # noqa: F811
    """The QA agent holds the answer back until it is scored, so this node writes it.

    Written here rather than by the agent because the agent runs once per attempt: a
    message written there would leave one unfaithful draft in the conversation for every
    retry the faithfulness gate spent.
    """
    actual_update = await finalize_turn(_state(qa_answer="creatine is well studied."))

    assert actual_update["final_message"] == "creatine is well studied."
    assert [message.content for message in actual_update["messages"]] == [
        "creatine is well studied."
    ]


async def test_a_branch_that_wrote_its_own_message_keeps_it(store) -> None:  # noqa: F811
    """``notify_fail`` and the refusals explain themselves; this node must not overwrite them."""
    actual_update = await finalize_turn(
        _state(final_message="no plan passed the checks")
    )

    assert actual_update["final_message"] == "no plan passed the checks"
    assert actual_update["messages"] == []
