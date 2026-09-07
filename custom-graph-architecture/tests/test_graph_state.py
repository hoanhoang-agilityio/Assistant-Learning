"""Tests for the workflow state schema.

The round-trip test is the important one: a state field that cannot be serialised breaks
the ``plan_approval`` interrupt gate, and it breaks it at resume time rather than at write time.
"""

import pytest
from langchain_core.messages import AIMessage, HumanMessage
from langgraph.graph import END, START, StateGraph
from langgraph.types import Command

from src.runtime.backends.memory import InMemoryRuntime
from src.schemas import GraphState, RetrievedChunk, initial_state, is_blocked

SPEC_FIELDS = {
    "user_id",
    "block_reason",
    "next",
    "iteration_count",
    "summary",
    "profile",
    "plan",
    "coach_retry_count",
    "verification_result",
    "pending_approval",
    "approval_decision",
    "approval_feedback",
    "approval_retry_count",
    "qa_answer",
    "retrieved_context",
    "faithfulness_score",
    "qa_retry_count",
}


def test_state_declares_every_field_in_the_spec() -> None:
    """docs/state-design.md is the contract; drifting from it should fail here."""
    declared = set(GraphState.__annotations__)

    assert SPEC_FIELDS <= declared
    assert "messages" in declared, "messages must be inherited from AgentState"


def test_only_the_inputs_are_required() -> None:
    """Everything a later node writes is optional, so early reads cannot KeyError."""
    assert GraphState.__required_keys__ == frozenset({"messages", "user_id"})


def test_initial_state_populates_every_key() -> None:
    """A run built this way never has to guard a read with ``.get()``."""
    state = initial_state("build me a plan", "user-1")

    assert SPEC_FIELDS <= set(state)
    assert state["user_id"] == "user-1"


def test_initial_state_zeroes_the_retry_counters() -> None:
    """All three retry limits in the spec count up from zero."""
    state = initial_state("hello", "user-1")

    assert state["coach_retry_count"] == 0
    assert state["approval_retry_count"] == 0
    assert state["qa_retry_count"] == 0
    assert state["iteration_count"] == 0


def test_initial_state_seeds_messages_with_the_query() -> None:
    """The turn's query enters the transcript as a human turn so agent nodes see it.

    A ``HumanMessage`` rather than a role dict: the supervisor decides what to route on by
    which messages are the user's own, and it reads the state a node is handed, which the
    reducer has already coerced.
    """

    state = initial_state("how much protein?", "user-1")

    assert state["messages"] == [HumanMessage(content="how much protein?")]


def test_initial_state_rejects_an_empty_user_id() -> None:
    """user_id scopes long-term memory; an empty one would cross user boundaries."""
    with pytest.raises(ValueError, match="user_id is required"):
        initial_state("hello", "")


async def test_messages_accumulate_across_nodes() -> None:
    """``messages`` keeps the inherited ``add_messages`` reducer — it appends, not replaces."""

    async def reply(state: GraphState) -> Command:
        return Command(update={"messages": [AIMessage(content="hi back")]}, goto=END)

    builder = StateGraph(GraphState)
    builder.add_node("reply", reply, destinations=(END,))
    builder.add_edge(START, "reply")

    result = await builder.compile(name="state_test").ainvoke(
        initial_state("hi", "user-1")
    )

    assert [type(message) for message in result["messages"]] == [
        HumanMessage,
        AIMessage,
    ]


async def test_state_round_trips_through_a_checkpointer() -> None:
    """Every field survives being checkpointed and read back — including nested chunks."""
    chunk: RetrievedChunk = {
        "text": "protein supports recovery",
        "source": "nutrition",
        "score": 0.91,
    }

    async def populate(state: GraphState) -> Command:
        return Command(
            update={
                "next": "qa_agent",
                "qa_answer": "1.6 g/kg",
                "retrieved_context": [chunk],
                "faithfulness_score": 0.93,
                "qa_retry_count": 1,
                "verification_result": {"passed": True, "errors": []},
                "pending_approval": {
                    "source": "coach_agent",
                    "kind": "plan",
                    "summary": "Approve this plan?",
                    "payload": {},
                },
            },
            goto=END,
        )

    builder = StateGraph(GraphState)
    builder.add_node("populate", populate, destinations=(END,))
    builder.add_edge(START, "populate")

    saver = await InMemoryRuntime().checkpointer()
    graph = builder.compile(checkpointer=saver, name="state_round_trip")
    config = {"configurable": {"thread_id": "state-round-trip"}}
    await graph.ainvoke(initial_state("how much protein?", "user-1"), config)

    restored = (await graph.aget_state(config)).values

    assert restored["next"] == "qa_agent"
    assert restored["retrieved_context"] == [chunk]
    assert restored["faithfulness_score"] == pytest.approx(0.93)
    assert restored["qa_retry_count"] == 1
    assert restored["verification_result"] == {"passed": True, "errors": []}
    assert restored["pending_approval"]["source"] == "coach_agent"


@pytest.mark.parametrize(
    ("block_reason", "expected"), [(None, False), ("banned topic", True)]
)
def test_is_blocked_reads_the_reason_not_a_flag(
    block_reason: str | None, expected: bool
) -> None:
    """`guard_blocked` was dropped: the reason alone tells routing whether to stop."""
    state = initial_state("hello", "user-1") | {"block_reason": block_reason}

    assert is_blocked(state) is expected


async def test_a_branch_update_leaves_other_branches_untouched() -> None:
    """Each field is written by one branch; a coaching write must not disturb QA fields."""

    async def coach(state: GraphState) -> Command:
        return Command(
            update={"coach_retry_count": state["coach_retry_count"] + 1}, goto=END
        )

    builder = StateGraph(GraphState)
    builder.add_node("coach", coach, destinations=(END,))
    builder.add_edge(START, "coach")

    result = await builder.compile(name="branch_test").ainvoke(
        initial_state("plan", "user-1")
    )

    assert result["coach_retry_count"] == 1
    assert result["qa_retry_count"] == 0
    assert result["qa_answer"] is None
