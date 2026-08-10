"""Tests for the QA agent.

The one agent the supervisor conversion did not change. It was already
``create_agent`` with middleware and no nodes, which is why it is the reference
for the two agents that were converted rather than something the conversion
touched.

What it gained is ``estimate_macros``, and the tests below are mostly about the
line that tool has to stay on: a what-if number is safe here because QA is
read-only and has no path to a save, and it must never become a second answer to
"what is my current protein target".
"""

import json
from pathlib import Path

import pytest
from langchain_core.messages import AIMessage, HumanMessage, ToolMessage

from app.core.langgraph.agents.qa import build_qa_agent
from app.core.langgraph.agents.qa.graph import _MAX_SEARCHES
from app.core.langgraph.agents.qa.tools import estimate_macros
from tests.conftest import FakeChatModel, stub_model, tool_call
from tests.support import call

PROFILE = {
    "weight_kg": 75.0,
    "height_cm": 175.0,
    "age": 28,
    "sex": "male",
    "activity_level": "light",
    "days_per_week": 3,
    "goal": "fat_loss",
}


def _state(**overrides) -> dict:
    """Build a QA state the agent and its tools can read."""
    return {
        "messages": [],
        "plan_context": "",
        "semantic_context": "",
        "episodic_context": "",
        "profile": dict(PROFILE),
        **overrides,
    }


@pytest.fixture(autouse=True)
def _no_knowledge_base(monkeypatch):
    """Answer every knowledge search with nothing, without a database."""

    async def no_passages(_query, top_k=4):
        return []

    monkeypatch.setattr("app.services.knowledge.knowledge_service.search", no_passages)


# ---------------------------------------------------------------------------
# Agent shape
# ---------------------------------------------------------------------------


def test_the_agent_is_declared_not_assembled(monkeypatch):
    """A model, its tools and a prompt — no hand-written nodes.

    Asserting the shape keeps the package honest: a ``nodes.py`` reappearing
    means someone rebuilt the loop ``create_agent`` already provides.
    """
    package = Path(__file__).resolve().parent.parent / "app/core/langgraph/agents/qa"
    assert {path.name for path in package.glob("*.py")} == {
        "__init__.py",
        "graph.py",
        "state.py",
        "tools.py",
    }

    stub_model(monkeypatch)
    agent = build_qa_agent()
    assert agent.name == "qa"
    assert {"model", "tools"} <= set(agent.get_graph().nodes)


async def test_the_agent_stops_searching_after_the_cap(monkeypatch):
    """A model that searches every turn must still end the turn.

    ``ToolCallLimitMiddleware`` is what stops it. Without a cap the only backstop
    is ``recursion_limit``, which ends the turn in an exception rather than an
    answer — the user asked a question and would get a stack trace.
    """
    fake = stub_model(
        monkeypatch,
        FakeChatModel(
            responses=[
                tool_call("search_knowledge", {"query": "creatine"}, f"c{index}")
                for index in range(_MAX_SEARCHES + 3)
            ],
            calls=[],
        ),
    )

    result = await build_qa_agent().ainvoke(
        _state(messages=[HumanMessage(content="is creatine worth it?")])
    )

    # Reaching this line at all is most of the assertion: without the limits the
    # run ends in `GraphRecursionError`, not a result.
    executed = [
        message
        for message in result["messages"]
        if isinstance(message, ToolMessage) and message.status != "error"
    ]
    assert len(executed) <= _MAX_SEARCHES, "the knowledge base was searched past the cap"
    assert len(fake.calls) <= _MAX_SEARCHES + 1, "the model kept being called past the cap"


async def test_tool_calls_survive_intact_across_rounds(monkeypatch):
    """The follow-up call must carry real messages, not flattened dicts.

    ``dump_messages`` renders a message as ``{role, content}``, which drops
    ``tool_calls`` from the assistant turn and ``tool_call_id`` from the result;
    the provider rejects that pair. While QA drove its own loop through
    ``llm_service`` it hit exactly that, so every question that did trigger a
    search fell through to the apology.
    """
    fake = stub_model(
        monkeypatch,
        FakeChatModel(
            responses=[
                tool_call("search_knowledge", {"query": "creatine"}, "c1"),
                AIMessage(content="Yes, 3-5 g a day."),
            ],
            calls=[],
        ),
    )

    result = await build_qa_agent().ainvoke(_state(messages=[HumanMessage(content="creatine?")]))

    assert result["messages"][-1].content == "Yes, 3-5 g a day."
    follow_up = fake.calls[1]
    assert any(getattr(m, "tool_calls", None) for m in follow_up), "tool_calls were dropped"
    assert any(isinstance(m, ToolMessage) and m.tool_call_id == "c1" for m in follow_up)


# ---------------------------------------------------------------------------
# estimate_macros
# ---------------------------------------------------------------------------


def test_an_estimate_says_it_is_one():
    """Two different numbers for the same question is worse than one general answer.

    The only thing keeping a what-if from being read as the user's real target is
    that it arrives labelled, with the assumption it rests on named beside it.
    """
    answer = json.loads(call(estimate_macros, _state(), sessions_per_week=5))

    assert answer["estimate"] is True
    assert answer["assumptions"]["sessions_per_week"] == 5
    assert "estimate" in answer["note"]


def test_an_estimate_defaults_to_the_stored_profile():
    """Only what the question changes is passed; the rest is what they have."""
    answer = json.loads(call(estimate_macros, _state(), goal="muscle_gain"))

    assert answer["assumptions"]["sessions_per_week"] == PROFILE["days_per_week"]
    assert answer["assumptions"]["weight_kg"] == PROFILE["weight_kg"]
    assert answer["assumptions"]["goal"] == "muscle_gain"


def test_more_sessions_raise_the_estimate():
    """The tool has to actually answer the question to be worth having."""
    three = json.loads(call(estimate_macros, _state(), sessions_per_week=3))
    five = json.loads(call(estimate_macros, _state(), sessions_per_week=5))

    assert five["macros"]["tdee"] > three["macros"]["tdee"]


def test_an_incomplete_profile_gets_the_general_form_not_a_number():
    """QA has no profile gate in front of it, deliberately, so this is ordinary.

    A question about pain must get an answer, not a form — so a missing field
    here produces guidance to answer in per-kg terms, never a raise and never an
    invented weight.
    """
    answer = call(estimate_macros, _state(profile={"goal": "fat_loss"}))

    assert "Not enough is known" in answer
    assert "per-kg" in answer
