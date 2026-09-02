"""Tests for the ``plan_approval`` interrupt gate: the coach agent's plan approval."""

from typing import Any

import pytest
from langchain_core.messages import HumanMessage
from langgraph.graph import END, START, StateGraph
from langgraph.types import Command

from src.configs.config import settings
from src.enums import PlanApprovalRoute
from src.nodes.plan_approval import (
    PLAN_APPROVAL_INTERRUPT,
    plan_approval,
    route_after_plan_approval,
)
from src.runtime.backends.memory import InMemoryRuntime
from src.schemas import GraphState, PendingApproval, initial_state

USER_ID = "user-1"


def _pending(summary: str = "Approve this?") -> PendingApproval:
    """One staged approval, as ``present_plan`` would leave it."""
    return PendingApproval(
        source="coach_agent", kind="plan", summary=summary, payload={}
    )


def _start() -> GraphState:
    """A run that reached the gate with one pending plan approval staged."""
    return initial_state("do something", USER_ID) | {"pending_approval": _pending()}


@pytest.fixture
async def graph():
    """A single-node graph that suspends at the gate."""
    runtime = InMemoryRuntime()
    builder = StateGraph(GraphState)
    builder.add_node("plan_approval", plan_approval)
    builder.add_edge(START, "plan_approval")
    builder.add_edge("plan_approval", END)

    yield builder.compile(
        checkpointer=await runtime.checkpointer(), name="plan_approval_test"
    )
    await runtime.close()


def _config(thread_id: str) -> dict[str, Any]:
    """Address one conversation's checkpoint."""
    return {"configurable": {"thread_id": thread_id}}


# --- The interrupt itself ---------------------------------------------------------------


async def test_the_run_suspends_instead_of_finishing(graph) -> None:
    """The graph stops at the gate rather than acting on the approval unattended."""
    config = _config("suspend")

    await graph.ainvoke(_start(), config)

    assert (await graph.aget_state(config)).next == ("plan_approval",)


async def test_the_interrupt_carries_the_pending_summary(graph) -> None:
    """The caller needs the summary to show the user what they're approving."""
    suspended = await graph.ainvoke(_start(), _config("payload"))

    interrupt_value = suspended["__interrupt__"][0].value
    assert interrupt_value["type"] == PLAN_APPROVAL_INTERRUPT
    assert interrupt_value["summary"] == "Approve this?"


async def test_an_approval_is_recorded_with_no_feedback(graph) -> None:
    """Approving needs nothing further from the caller."""
    config = _config("approve")
    await graph.ainvoke(_start(), config)

    resumed = await graph.ainvoke(Command(resume="approve"), config)

    assert resumed["approval_decision"] == "approve"
    assert resumed["approval_feedback"] is None


async def test_a_structured_approval_is_recognised(graph) -> None:
    """A client resuming with a decision object instead of prose must still approve."""
    config = _config("structured-approve")
    await graph.ainvoke(_start(), config)

    resumed = await graph.ainvoke(Command(resume={"decision": "approve"}), config)

    assert resumed["approval_decision"] == "approve"
    assert resumed["approval_feedback"] is None


async def test_a_structured_rejection_keeps_its_feedback(graph) -> None:
    """The coach agent needs the reviewer's actual words to revise the plan."""
    config = _config("structured-reject")
    await graph.ainvoke(_start(), config)

    resumed = await graph.ainvoke(
        Command(resume={"decision": "reject", "feedback": "too much volume on day 1"}),
        config,
    )

    assert resumed["approval_decision"] == "reject"
    assert resumed["approval_feedback"] == "too much volume on day 1"


async def test_free_text_that_is_not_an_approval_is_a_rejection_with_feedback(
    graph,
) -> None:
    """A reviewer typing a comment instead of a keyword is rejecting with that comment."""
    config = _config("free-text-reject")
    await graph.ainvoke(_start(), config)

    resumed = await graph.ainvoke(Command(resume="swap the bench press"), config)

    assert resumed["approval_decision"] == "reject"
    assert resumed["approval_feedback"] == "swap the bench press"


async def test_a_rejection_with_no_feedback_leaves_it_none(graph) -> None:
    """No feedback is a distinct case from feedback that happens to be empty."""
    config = _config("no-feedback")
    await graph.ainvoke(_start(), config)

    resumed = await graph.ainvoke(Command(resume={"decision": "reject"}), config)

    assert resumed["approval_decision"] == "reject"
    assert resumed["approval_feedback"] is None


async def test_the_decision_is_recorded_in_the_transcript(graph) -> None:
    """The reviewer's reply becomes part of the conversation, like any other turn."""
    config = _config("transcript")
    await graph.ainvoke(_start(), config)

    resumed = await graph.ainvoke(Command(resume="swap the bench press"), config)

    assert isinstance(resumed["messages"][-1], HumanMessage)
    assert resumed["messages"][-1].content == "swap the bench press"


async def test_the_run_finishes_once_reviewed(graph) -> None:
    """Resuming clears the gate rather than suspending a second time."""
    config = _config("finish")
    await graph.ainvoke(_start(), config)

    await graph.ainvoke(Command(resume="approve"), config)

    assert (await graph.aget_state(config)).next == ()


# --- Retry counting ----------------------------------------------------------------------


async def test_a_rejection_with_feedback_spends_an_attempt(graph) -> None:
    """Only a genuine revision request counts against the retry budget."""
    config = _config("count-revise")
    await graph.ainvoke(_start(), config)

    resumed = await graph.ainvoke(Command(resume="swap the bench press"), config)

    assert resumed["approval_retry_count"] == 1


async def test_an_approval_does_not_spend_an_attempt(graph) -> None:
    """Approving is not a revision, so it must not eat into the budget."""
    config = _config("count-approve")
    await graph.ainvoke(_start(), config)

    resumed = await graph.ainvoke(Command(resume="approve"), config)

    assert resumed["approval_retry_count"] == 0


async def test_a_rejection_with_no_feedback_does_not_spend_an_attempt(graph) -> None:
    """There is nothing to revise from, so this is not a revision attempt either."""
    config = _config("count-no-feedback")
    await graph.ainvoke(_start(), config)

    resumed = await graph.ainvoke(Command(resume={"decision": "reject"}), config)

    assert resumed["approval_retry_count"] == 0


# --- Routing: all four outcomes -------------------------------------------------------------


def _reviewed(
    decision: str | None,
    feedback: str | None = None,
    retry_count: int = 0,
) -> GraphState:
    """State as it stands right after the gate records a decision."""
    return initial_state("do something", USER_ID) | {
        "pending_approval": _pending(),
        "approval_decision": decision,
        "approval_feedback": feedback,
        "approval_retry_count": retry_count,
    }


def test_an_approval_commits_the_plan() -> None:
    """The only way a plan reaches the user's stored plans."""
    state = _reviewed("approve")
    assert route_after_plan_approval(state) == PlanApprovalRoute.COACH_APPROVE


def test_a_rejection_with_feedback_revises() -> None:
    """Feedback is what the coach agent needs to act on the rejection."""
    state = _reviewed("reject", "fix it")
    assert route_after_plan_approval(state) == PlanApprovalRoute.COACH_REVISE


def test_a_rejection_with_no_feedback_stops_the_run() -> None:
    """Nothing to revise from means there is nothing productive left to do."""
    state = _reviewed("reject", None)
    assert route_after_plan_approval(state) == PlanApprovalRoute.COACH_NO_FEEDBACK


def test_no_feedback_wins_over_an_exhausted_budget() -> None:
    """A reviewer who never gives feedback should not be told they revised too many times."""
    state = _reviewed("reject", None, settings.HITL_MAX_RETRIES)
    assert route_after_plan_approval(state) == PlanApprovalRoute.COACH_NO_FEEDBACK


@pytest.mark.parametrize(
    ("retry_count", "expected"),
    [
        (0, PlanApprovalRoute.COACH_REVISE),
        (settings.HITL_MAX_RETRIES - 1, PlanApprovalRoute.COACH_REVISE),
        (settings.HITL_MAX_RETRIES, PlanApprovalRoute.COACH_EXHAUSTED),
        (settings.HITL_MAX_RETRIES + 1, PlanApprovalRoute.COACH_EXHAUSTED),
    ],
)
def test_a_rejection_with_feedback_routes_on_the_budget(
    retry_count: int, expected: PlanApprovalRoute
) -> None:
    """Back to the coach while there are attempts left, and to ``hitl_exhausted`` after."""
    state = _reviewed("reject", "fix it", retry_count)
    assert route_after_plan_approval(state) == expected
