"""The QA branch end to end: answer, score, retry, and fall back when nothing scores.

Runs the real compiled graph from a QA question through ``ragas_verification``. The QA agent
is stubbed — its own contract is covered in ``test_qa_agent.py`` — and so is the faithfulness
judge, whose contract is covered in ``test_ragas_verification.py``. What is under test here is
the loop they sit in: that no answer reaches the end of a run unscored, that a rejected one
goes back to the agent with the reason, and that the loop stops instead of running forever.
"""

import pytest
from langchain_core.messages import AIMessage, ToolMessage

import src.services.profile as profile_service
from src.core.configs.config import settings
from src.core.langgraph.agents import qa as qa_module
from src.core.langgraph.graph import build_graph
from src.core.langgraph.nodes import intent as intent_node
from src.core.langgraph.nodes import ragas as ragas_node
from src.core.langgraph.nodes.qa_fallback import (
    QA_FALLBACK_NO_CONTEXT,
    QA_FALLBACK_UNSUPPORTED,
    build_qa_fallback_message,
)
from src.core.langgraph.runtime import MemoryScope, namespace_for
from src.core.langgraph.runtime.backends.memory import InMemoryRuntime
from src.schemas import RetrievedChunk, initial_state
from src.services.profile import PROFILE_KEY
from tests.test_verification_gate import PROFILE

USER_ID = "user-qa-loop"
CONFIG = {"configurable": {"thread_id": "qa-loop"}}

QUESTION = "How much protein should I eat?"
ANSWER = "Aim for 1.6 g of protein per kg of bodyweight per day."

PASSAGES: list[RetrievedChunk] = [
    {
        "text": "Protein intake of 1.6 g/kg/day maximises training adaptation.",
        "source": "nutrition.docx",
        "score": 0.82,
    }
]

BELOW_THRESHOLD = settings.RAGAS_FAITHFULNESS_THRESHOLD - 0.4


class _StubAgent:
    """Stands in for the compiled QA agent: the same answer and passages every time."""

    def __init__(self, passages: list[RetrievedChunk]) -> None:
        self.passages = passages
        self.calls: list[list] = []

    async def ainvoke(self, inputs: dict, context: object) -> dict:
        self.calls.append(inputs["messages"])
        retrieval = ToolMessage(
            content="[]",
            name="search_knowledge",
            tool_call_id=f"call-{len(self.calls)}",
            artifact=self.passages,
        )
        return {"messages": [retrieval, AIMessage(content=ANSWER)]}


@pytest.fixture
async def loop(monkeypatch: pytest.MonkeyPatch):
    """The real graph on the QA branch, with the agent and the judge under test control."""

    async def classify_as_qa(_: str) -> str:
        return "qa"

    runtime = InMemoryRuntime()
    monkeypatch.setattr(profile_service, "graph_runtime", runtime)
    monkeypatch.setattr(intent_node, "classify_user_intent", classify_as_qa)

    store = await runtime.store()
    await store.aput(
        namespace_for(USER_ID, MemoryScope.FACTS),
        PROFILE_KEY,
        PROFILE.model_dump(mode="json"),
    )

    graph = build_graph().compile(
        checkpointer=await runtime.checkpointer(), name="qa_loop_test"
    )

    def build(
        passages: list[RetrievedChunk] = PASSAGES,
        scores: list[float] | None = None,
    ):
        """Serve an agent that retrieves ``passages`` and a judge that returns ``scores``."""
        agent = _StubAgent(passages)
        monkeypatch.setattr(qa_module, "build_qa_agent", lambda: agent)

        remaining = list(scores or [])

        async def score_faithfulness(**kwargs: object) -> float | None:
            graph.scored.append(kwargs)
            return remaining.pop(0) if remaining else BELOW_THRESHOLD

        monkeypatch.setattr(ragas_node, "score_faithfulness", score_faithfulness)
        graph.agent = agent
        return graph

    graph.scored = []
    graph.build = build
    yield graph
    await runtime.close()


async def _ask(graph) -> dict:
    """Ask the question and run the branch to wherever it ends."""
    return await graph.ainvoke(initial_state(QUESTION, USER_ID), CONFIG)


# --- A faithful answer --------------------------------------------------------------------


async def test_a_faithful_answer_ends_the_run(loop) -> None:
    """The passing path: one answer, one score, done."""
    graph = loop.build(scores=[1.0])

    result = await _ask(graph)

    assert result["qa_answer"] == ANSWER
    assert result["ragas_score"] == 1.0
    assert result["qa_retry_count"] == 0
    assert (await graph.aget_state(CONFIG)).next == ()


async def test_the_answer_is_scored_against_what_the_agent_retrieved(loop) -> None:
    """The gate has to see this turn's passages; scoring against anything else proves nothing."""
    graph = loop.build(scores=[1.0])

    await _ask(graph)

    assert graph.scored == [
        {"question": QUESTION, "answer": ANSWER, "passages": PASSAGES}
    ]


async def test_no_answer_reaches_the_end_of_a_run_unscored(loop) -> None:
    """``qa_agent`` no longer runs to `END`; every answer passes the gate on its way out."""
    graph = loop.build(scores=[1.0])

    await _ask(graph)

    assert len(graph.scored) == 1


# --- An unfaithful answer -----------------------------------------------------------------


async def test_an_unfaithful_answer_goes_back_to_the_agent(loop) -> None:
    """The retry is the point of the gate: a second attempt at the same question."""
    graph = loop.build(scores=[BELOW_THRESHOLD, 1.0])

    result = await _ask(graph)

    assert len(graph.agent.calls) == 2
    assert result["ragas_score"] == 1.0
    assert result["qa_retry_count"] == 0


async def test_the_retry_tells_the_agent_what_was_rejected_and_what_it_scored(
    loop,
) -> None:
    """A retry that does not say what was wrong is just the same question asked twice."""
    graph = loop.build(scores=[BELOW_THRESHOLD, 1.0])

    await _ask(graph)

    retry_context = str(graph.agent.calls[1][-1].content)
    assert ANSWER in retry_context
    assert f"{BELOW_THRESHOLD:.2f}" in retry_context


# --- The bounded loop ---------------------------------------------------------------------


async def test_an_answer_that_never_scores_ends_at_the_fallback(loop) -> None:
    """Without the counter this loop never terminates: answer, reject, answer again."""
    graph = loop.build()

    result = await _ask(graph)

    assert len(graph.agent.calls) == settings.QA_MAX_RETRIES
    assert result["qa_retry_count"] == settings.QA_MAX_RETRIES
    assert result["final_message"] == build_qa_fallback_message(PASSAGES)
    assert (await graph.aget_state(CONFIG)).next == ()


async def test_the_fallback_does_not_hand_back_the_answer_the_gate_rejected(
    loop,
) -> None:
    """The run ends refusing to answer, so nothing may still be holding the refused answer."""
    graph = loop.build()

    result = await _ask(graph)

    assert result["qa_answer"] is None
    assert result["final_message"].startswith(QA_FALLBACK_UNSUPPORTED)


async def test_a_question_the_knowledge_base_is_silent_on_ends_saying_so(loop) -> None:
    """Retrieval returning nothing is a different failure, and the user is told which."""
    graph = loop.build(passages=[])

    result = await _ask(graph)

    assert result["final_message"].startswith(QA_FALLBACK_NO_CONTEXT)
    assert (await graph.aget_state(CONFIG)).next == ()
