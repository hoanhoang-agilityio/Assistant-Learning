"""Tests for the ``hitl_review`` interrupt gate."""

import sys
from typing import Any

import pytest
from langchain_core.messages import HumanMessage
from langgraph.graph import END, START, StateGraph
from langgraph.types import Command

from src.core.configs.config import settings
from src.core.langgraph.nodes.hitl_review import (
    HITL_REVIEW_INTERRUPT,
    hitl_review,
    route_after_hitl_review,
)
from src.core.langgraph.runtime.backends.memory import InMemoryRuntime
from src.schemas import GraphState, initial_state
from tests.test_load_context import USER_ID
from tests.test_verification_completeness import complete_plan

hitl_review_module = sys.modules[hitl_review.__module__]

PLAN = complete_plan().model_dump(mode="json")
TODO_IN_PROGRESS = [{"id": 1, "task": "Set the calorie target.", "status": "in_progress"}]


@pytest.fixture(autouse=True)
def _stub_plan_markdown(monkeypatch: pytest.MonkeyPatch) -> None:
    """Render the plan is covered by ``plan_presentation``'s own tests; stub it out here."""

    async def render_plan_markdown(plan: Any) -> str:
        return "PLAN_MARKDOWN"

    monkeypatch.setattr(hitl_review_module, "render_plan_markdown", render_plan_markdown)


@pytest.fixture
async def graph():
    """A single-node graph that suspends at the review gate."""
    runtime = InMemoryRuntime()
    builder = StateGraph(GraphState)
    builder.add_node("hitl_review", hitl_review)
    builder.add_edge(START, "hitl_review")
    builder.add_edge("hitl_review", END)

    yield builder.compile(
        checkpointer=await runtime.checkpointer(), name="hitl_review_test"
    )
    await runtime.close()


def _config(thread_id: str) -> dict[str, Any]:
    """Address one conversation's checkpoint."""
    return {"configurable": {"thread_id": thread_id}}


def _start() -> GraphState:
    """A run that reached the gate with a plan already generated and verified."""
    return initial_state("build me a plan", USER_ID) | {
        "plan": PLAN,
        "todo": TODO_IN_PROGRESS,
    }


async def test_the_run_suspends_instead_of_finishing(graph) -> None:
    """The graph stops at the gate rather than handing the plan straight back."""
    config = _config("suspend")

    await graph.ainvoke(_start(), config)

    assert (await graph.aget_state(config)).next == ("hitl_review",)


async def test_the_interrupt_carries_the_plan_to_review(graph) -> None:
    """The caller needs the plan itself to show the user what they're approving."""
    suspended = await graph.ainvoke(_start(), _config("payload"))

    interrupt_value = suspended["__interrupt__"][0].value
    assert interrupt_value["type"] == HITL_REVIEW_INTERRUPT
    assert interrupt_value["plan"] == PLAN


async def test_an_approval_is_recorded_with_no_feedback(graph) -> None:
    """Approving needs nothing further from the user."""
    config = _config("approve")
    await graph.ainvoke(_start(), config)

    resumed = await graph.ainvoke(Command(resume="approve"), config)

    assert resumed["hitl_decision"] == "approve"
    assert resumed["hitl_feedback"] is None


async def test_a_structured_approval_is_recognised(graph) -> None:
    """A client resuming with a decision object instead of prose must still approve."""
    config = _config("structured-approve")
    await graph.ainvoke(_start(), config)

    resumed = await graph.ainvoke(Command(resume={"decision": "approve"}), config)

    assert resumed["hitl_decision"] == "approve"
    assert resumed["hitl_feedback"] is None


async def test_a_structured_rejection_keeps_its_feedback(graph) -> None:
    """The coach agent needs the reviewer's actual words to revise the plan."""
    config = _config("structured-reject")
    await graph.ainvoke(_start(), config)

    resumed = await graph.ainvoke(
        Command(resume={"decision": "reject", "feedback": "too much volume on day 1"}),
        config,
    )

    assert resumed["hitl_decision"] == "reject"
    assert resumed["hitl_feedback"] == "too much volume on day 1"


async def test_free_text_that_is_not_an_approval_is_a_rejection_with_feedback(
    graph,
) -> None:
    """A reviewer typing a comment instead of a keyword is rejecting with that comment."""
    config = _config("free-text-reject")
    await graph.ainvoke(_start(), config)

    resumed = await graph.ainvoke(Command(resume="swap the bench press"), config)

    assert resumed["hitl_decision"] == "reject"
    assert resumed["hitl_feedback"] == "swap the bench press"


async def test_a_rejection_with_no_feedback_leaves_it_none(graph) -> None:
    """No feedback is a distinct case from feedback that happens to be empty."""
    config = _config("no-feedback")
    await graph.ainvoke(_start(), config)

    resumed = await graph.ainvoke(Command(resume={"decision": "reject"}), config)

    assert resumed["hitl_decision"] == "reject"
    assert resumed["hitl_feedback"] is None


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


# --- Todo status ------------------------------------------------------------------------


async def test_an_approval_marks_the_todo_done(graph) -> None:
    """The list is only finished once the user accepts what it produced."""
    config = _config("todo-approve")
    await graph.ainvoke(_start(), config)

    resumed = await graph.ainvoke(Command(resume="approve"), config)

    assert resumed["todo"] == [{**TODO_IN_PROGRESS[0], "status": "done"}]


async def test_a_rejection_leaves_the_todo_in_progress(graph) -> None:
    """A revision is still being worked, so the list is not done yet."""
    config = _config("todo-reject")
    await graph.ainvoke(_start(), config)

    resumed = await graph.ainvoke(Command(resume="swap the bench press"), config)

    assert resumed["todo"] == TODO_IN_PROGRESS


# --- Retry counting -------------------------------------------------------------------


async def test_a_rejection_with_feedback_spends_an_attempt(graph) -> None:
    """Only a genuine revision request counts against the retry budget."""
    config = _config("count-revise")
    await graph.ainvoke(_start(), config)

    resumed = await graph.ainvoke(Command(resume="swap the bench press"), config)

    assert resumed["hitl_retry_count"] == 1


async def test_an_approval_does_not_spend_an_attempt(graph) -> None:
    """Approving is not a revision, so it must not eat into the budget."""
    config = _config("count-approve")
    await graph.ainvoke(_start(), config)

    resumed = await graph.ainvoke(Command(resume="approve"), config)

    assert resumed["hitl_retry_count"] == 0


async def test_a_rejection_with_no_feedback_does_not_spend_an_attempt(graph) -> None:
    """There is nothing to revise from, so this is not a revision attempt either."""
    config = _config("count-no-feedback")
    await graph.ainvoke(_start(), config)

    resumed = await graph.ainvoke(Command(resume={"decision": "reject"}), config)

    assert resumed["hitl_retry_count"] == 0


# --- Routing ---------------------------------------------------------------------------


def _reviewed(
    decision: str, feedback: str | None = None, retry_count: int = 0
) -> GraphState:
    """State as it stands right after the gate records a decision."""
    return initial_state("build me a plan", USER_ID) | {
        "hitl_decision": decision,
        "hitl_feedback": feedback,
        "hitl_retry_count": retry_count,
    }


def test_an_approval_routes_to_the_end() -> None:
    """The only way a plan reaches the user."""
    assert route_after_hitl_review(_reviewed("approve")) == "approve"


def test_a_rejection_with_feedback_routes_to_a_revision() -> None:
    """Feedback is what the coach agent needs to act on the rejection."""
    assert route_after_hitl_review(_reviewed("reject", "fix it")) == "revise"


def test_a_rejection_with_no_feedback_stops_the_run() -> None:
    """Nothing to revise from means there is nothing productive left to do."""
    assert route_after_hitl_review(_reviewed("reject", None)) == "no_feedback"


def test_no_feedback_wins_over_an_exhausted_budget() -> None:
    """A reviewer who never gives feedback should not be told they revised too many times."""
    state = _reviewed("reject", None, settings.HITL_MAX_RETRIES)

    assert route_after_hitl_review(state) == "no_feedback"


@pytest.mark.parametrize(
    ("retry_count", "expected"),
    [
        (0, "revise"),
        (settings.HITL_MAX_RETRIES - 1, "revise"),
        (settings.HITL_MAX_RETRIES, "exhausted"),
        (settings.HITL_MAX_RETRIES + 1, "exhausted"),
    ],
)
def test_a_rejection_with_feedback_routes_on_the_budget(
    retry_count: int, expected: str
) -> None:
    """Back to the coach while there are attempts left, and to ``hitl_exhausted`` after."""
    state = _reviewed("reject", "fix it", retry_count)

    assert route_after_hitl_review(state) == expected
