"""What one turn hands back: its replies, deduplicated, and the steps it reports on the way.

The seam between the graph and the chat API. Every retry a turn spends leaves its own
trace in ``messages``, and the interrupt gates ask a question that is usually already in
there — so this is where a turn either says one thing or says it three times.
"""

from types import SimpleNamespace

import pytest
from langchain_core.messages import AIMessage, HumanMessage

from src.enums import Node, StreamEventType
from src.nodes.present_plan import (
    PLAN_READY_MESSAGE,
    PLAN_REVIEW_ASK,
    present_plan,
)
from src.runtime.facade import (
    _interrupt_text,
    _pending_interrupt_value,
    _resume_value,
    _step_events,
    _turn_reply,
)
from src.schemas import GraphState
from src.services import plan_presentation
from tests.test_verification_completeness import CATALOGUE, complete_plan

SUMMARY = "A four day upper/lower plan for fat loss."


@pytest.fixture
def catalogue(monkeypatch: pytest.MonkeyPatch) -> None:
    """Resolve a plan's exercise ids from the fixture catalogue rather than the database."""

    async def fetch_exercises_by_id(exercise_ids: list[str]) -> dict:
        return {
            exercise_id: CATALOGUE[exercise_id]
            for exercise_id in exercise_ids
            if exercise_id in CATALOGUE
        }

    monkeypatch.setattr(
        plan_presentation, "fetch_exercises_by_id", fetch_exercises_by_id
    )


def _state(messages: list, *, interrupt: str | None = None) -> SimpleNamespace:
    """A settled or suspended graph state, as ``aget_state`` returns one."""
    if interrupt is None:
        return SimpleNamespace(values={"messages": messages}, next=(), tasks=())
    task = SimpleNamespace(interrupts=(SimpleNamespace(value={"summary": interrupt}),))
    return SimpleNamespace(
        values={"messages": messages}, next=("hitl_review",), tasks=(task,)
    )


# --- One turn, one answer ------------------------------------------------------------


def test_the_reader_hands_back_every_reply_the_turn_wrote() -> None:
    """Faithful by design: holding a turn to one reply is the nodes' job, not this reader's.

    A node that writes a message for an attempt which has not yet cleared its gate leaves
    one rejected draft per retry, and this is where all of them would surface. Keeping
    the reader faithful is what makes that a visible bug in the node rather than
    something papered over here — ``test_hitl_loop`` asserts the count the graph
    actually produces.
    """
    state = _state(
        [
            HumanMessage(content="build me a plan"),
            AIMessage(content=SUMMARY),
            AIMessage(content=SUMMARY),
        ]
    )

    assert [reply.content for reply in _turn_reply(state, before=0)] == [SUMMARY] * 2


def test_the_users_own_message_is_not_read_back_as_a_reply() -> None:
    """A fresh turn is invoked with the user's message, so it lands in the new slice too."""
    state = _state([HumanMessage(content="build me a plan"), AIMessage(content="ok")])

    assert [reply.content for reply in _turn_reply(state, before=0)] == ["ok"]


def test_only_what_this_turn_added_is_returned() -> None:
    """The conversation before ``before`` was already shown."""
    state = _state([AIMessage(content="older"), AIMessage(content="newer")])

    assert [reply.content for reply in _turn_reply(state, before=1)] == ["newer"]


# --- The question a pause is asking --------------------------------------------------


def test_a_pending_question_already_in_the_conversation_is_not_repeated() -> None:
    """``present_plan`` writes the ask so it survives a reload; appending it would double it."""
    state = _state(
        [AIMessage(content=f"the plan\n\n{PLAN_REVIEW_ASK}")],
        interrupt=PLAN_REVIEW_ASK,
    )

    replies = _turn_reply(state, before=0)

    assert [reply.content for reply in replies] == [f"the plan\n\n{PLAN_REVIEW_ASK}"]


def test_a_pending_question_nothing_carries_is_appended() -> None:
    """A gate whose question no node wrote still has to reach the user."""
    state = _state([AIMessage(content="the plan")], interrupt=PLAN_REVIEW_ASK)

    replies = _turn_reply(state, before=0)

    assert [reply.content for reply in replies] == ["the plan", PLAN_REVIEW_ASK]


def test_a_settled_run_asks_nothing() -> None:
    """No pause, no question."""
    assert len(_turn_reply(_state([AIMessage(content="done")]), before=0)) == 1


# --- Steps ---------------------------------------------------------------------------


def test_a_named_node_is_reported_as_a_step() -> None:
    """What the user watches happen is the node table, not the graph's own names."""
    events = _step_events({Node.COACH_AGENT: {"plan": {}}})

    assert len(events) == 1
    assert events[0].type == StreamEventType.STEP
    assert events[0].node == Node.COACH_AGENT
    assert events[0].label


def test_an_unnamed_node_is_reported_as_nothing() -> None:
    """A node added to the graph cannot leak its internal name into the UI by default."""
    assert _step_events({Node.BLOCKED: {}}) == []


def test_langgraphs_own_keys_are_not_steps() -> None:
    """``__interrupt__`` arrives on the same channel and is not a node."""
    assert _step_events({"__interrupt__": ()}) == []


# --- Presenting the plan -------------------------------------------------------------


async def test_the_plan_is_written_into_the_conversation(catalogue: None) -> None:
    """The rendered plan lived only in the interrupt payload, so a reload lost it."""
    plan = complete_plan().model_dump(mode="json") | {"summary": SUMMARY}

    update = await present_plan(
        GraphState(messages=[], user_query="", user_id="u", plan=plan)
    )

    assert len(update["messages"]) == 1
    written = update["messages"][0].content
    assert written.startswith(SUMMARY)
    assert written.endswith(PLAN_REVIEW_ASK)


@pytest.mark.parametrize("plan", [None, {}])
async def test_a_missing_plan_still_asks_for_a_decision(plan: dict | None) -> None:
    """The review gate is about to suspend either way; it must not suspend in silence."""
    update = await present_plan(
        GraphState(messages=[], user_query="", user_id="u", plan=plan)
    )

    assert update["messages"][0].content == f"{PLAN_READY_MESSAGE}\n\n{PLAN_REVIEW_ASK}"


# --- Resuming a HumanInTheLoopMiddleware pause ----------------------------------------


def _hitl_state(*, description: str = "Tool: update_user_profile") -> SimpleNamespace:
    """A run suspended on ``update_user_profile``'s overwrite approval."""
    payload = {
        "action_requests": [
            {"name": "update_user_profile", "args": {}, "description": description}
        ],
        "review_configs": [
            {
                "action_name": "update_user_profile",
                "allowed_decisions": ["approve", "reject"],
            }
        ],
    }
    task = SimpleNamespace(interrupts=(SimpleNamespace(value=payload),))
    return SimpleNamespace(values={"messages": []}, next=("user_agent",), tasks=(task,))


def test_a_hitl_requests_description_is_the_question() -> None:
    """The middleware's own action description is what the user is shown."""
    state = _hitl_state(description="age is already 30. Update it to 34?")

    assert (
        _interrupt_text(_pending_interrupt_value(state))
        == "age is already 30. Update it to 34?"
    )


def test_approving_a_hitl_pause_resumes_with_an_approve_decision() -> None:
    """A plain 'approve' reply becomes the middleware's own decision shape."""
    state = _hitl_state()

    assert _resume_value(state, "approve", None) == {"decisions": [{"type": "approve"}]}


def test_rejecting_a_hitl_pause_carries_the_free_text_as_the_message() -> None:
    """Anything else is a rejection, with the reviewer's own words attached."""
    state = _hitl_state()

    assert _resume_value(state, "no, leave it", None) == {
        "decisions": [{"type": "reject", "message": "no, leave it"}]
    }


def test_a_submitted_form_still_wins_over_a_hitl_pause() -> None:
    """Form submission is a distinct resume channel and must not be reinterpreted as text."""
    state = _hitl_state()

    assert _resume_value(state, "approve", {"age": 34}) == {"age": 34}


def test_a_plain_pause_still_resumes_with_the_reply_as_is() -> None:
    """The plan-approval gate reads a raw string, not a ``HumanInTheLoopMiddleware`` decision."""
    state = _state([AIMessage(content="the plan")], interrupt="Approve this?")

    assert _resume_value(state, "approve", None) == "approve"
