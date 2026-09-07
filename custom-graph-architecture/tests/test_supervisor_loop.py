"""The supervisor loop end to end: a compound query that needs two agents in one turn.

Every agent and judge underneath the supervisor has its own contract tested elsewhere
(``test_qa_agent.py``, ``test_coach_agent.py``, ``test_verify_faithfulness.py``,
``test_verification_gate.py``, ``test_supervisor.py``). What is under test here is the loop
itself: that a request needing both ``qa_agent`` and ``coach_agent`` actually reaches both in
one turn rather than stopping after the first, and that it resolves the read-only QA part
before the part that ends in an approval interrupt — per ``supervisor-migration.md`` §3, so a
compound request is not split across two user turns by an interrupt that lands first.
"""

import sys
from typing import Any

import pytest
from langchain_core.messages import AIMessage, ToolMessage

import src.agents.coach as coach_module
import src.agents.qa as qa_module
import src.nodes.verification as verification_module
import src.services.memory as memory_service
from src.agents.supervisor import SupervisorDecision, supervisor
from src.graph import build_graph
from src.nodes import faithfulness as faithfulness_node
from src.nodes.present_plan import present_plan
from src.runtime import MemoryScope, namespace_for
from src.runtime.backends.memory import InMemoryRuntime
from src.schemas import RetrievedChunk, VerificationResult, initial_state
from src.services.profile import PROFILE_KEY
from tests.test_verification_completeness import PROFILE, complete_plan

supervisor_module = sys.modules[supervisor.__module__]
present_plan_module = sys.modules[present_plan.__module__]

USER_ID = "user-supervisor-loop"
CONFIG = {"configurable": {"thread_id": "supervisor-loop"}}

QUESTION = "How much protein should I eat, and can you also build me a training plan?"
ANSWER = "Aim for 1.6 g of protein per kg of bodyweight per day."

PASSAGES: list[RetrievedChunk] = [
    {
        "text": "Protein intake of 1.6 g/kg/day maximises training adaptation.",
        "source": "nutrition.docx",
        "score": 0.82,
    }
]

PLAN = complete_plan()


class _StubQaAgent:
    """Stands in for the compiled QA agent: one retrieval, one answer."""

    def __init__(self) -> None:
        self.calls = 0

    async def ainvoke(self, inputs: dict, context: object) -> dict:
        self.calls += 1
        retrieval = ToolMessage(
            content="[]",
            name="search_knowledge",
            tool_call_id=f"call-{self.calls}",
            artifact=PASSAGES,
        )
        return {"messages": [retrieval, AIMessage(content=ANSWER)]}


class _StubCoachAgent:
    """Stands in for the compiled coach agent: one already-valid plan, every time."""

    def __init__(self) -> None:
        self.calls = 0

    async def ainvoke(self, inputs: dict, context: object) -> dict:
        self.calls += 1
        return {"messages": [], "structured_response": PLAN}


class _ScriptedSupervisor:
    """Serves one routing decision per call, in the order a real supervisor would choose."""

    def __init__(self, decisions: list[str]) -> None:
        self.remaining = list(decisions)
        self.order: list[str] = []

    def with_retry(self, **_: object) -> "_ScriptedSupervisor":
        return self

    async def ainvoke(self, _messages: list) -> SupervisorDecision:
        decision = self.remaining.pop(0)
        self.order.append(decision)
        return SupervisorDecision(next=decision)


class _FakeChatModel:
    def __init__(self, structured: _ScriptedSupervisor) -> None:
        self.structured = structured

    def with_structured_output(self, _schema: type) -> _ScriptedSupervisor:
        return self.structured


@pytest.fixture
async def loop(monkeypatch: pytest.MonkeyPatch):
    """The real graph, with every model call under test control and a stored profile."""

    runtime = InMemoryRuntime()
    monkeypatch.setattr(memory_service, "graph_runtime", runtime)

    store = await runtime.store()
    await store.aput(
        namespace_for(USER_ID, MemoryScope.FACTS),
        PROFILE_KEY,
        PROFILE.model_dump(mode="json"),
    )

    # Deterministic verification's own rules are covered in ``test_verification_gate.py`` and
    # its siblings; here the plan only needs to pass so the run reaches ``present_plan``.
    async def verify_plan(*_args: object, **_kwargs: object) -> VerificationResult:
        return VerificationResult(issues=[])

    monkeypatch.setattr(verification_module, "verify_plan", verify_plan)

    # Rendering pulls exercise names from the catalogue store, which is not under test here
    # (``test_plan_presentation.py`` covers it); a plain stand-in keeps this test off it.
    async def render_plan_markdown(_plan: object) -> str:
        return "Your training plan is ready."

    monkeypatch.setattr(
        present_plan_module, "render_plan_markdown", render_plan_markdown
    )

    # The judge's own thresholding is covered in ``test_verify_faithfulness.py``; here the
    # answer only needs to pass so the run moves on instead of retrying.
    async def score_faithfulness(**_kwargs: object) -> float:
        return 1.0

    monkeypatch.setattr(faithfulness_node, "score_faithfulness", score_faithfulness)

    qa_agent = _StubQaAgent()
    coach_agent = _StubCoachAgent()
    monkeypatch.setattr(qa_module, "build_qa_agent", lambda: qa_agent)
    monkeypatch.setattr(coach_module, "build_coach_agent", lambda: coach_agent)

    scripted = _ScriptedSupervisor(["qa_agent", "coach_agent"])
    monkeypatch.setattr(
        supervisor_module, "chat_model", lambda **_: _FakeChatModel(scripted)
    )

    graph = build_graph().compile(
        checkpointer=await runtime.checkpointer(), name="supervisor_loop_test"
    )
    graph.qa_agent = qa_agent
    graph.coach_agent = coach_agent
    graph.supervisor = scripted

    yield graph
    await runtime.close()


async def _ask(graph) -> dict[str, Any]:
    """Ask the compound question and run the turn to wherever it ends.

    ``profile`` is seeded directly in state rather than left for the run to load: nothing
    between ``supervisor``, ``qa_agent`` and ``coach_agent`` loads it — only ``user_agent``'s
    ``get_user_profile``/``update_user_profile`` tools read long-term memory into state, and
    this scenario never routes there. In a real conversation the checkpointer would carry a
    profile ``user_agent`` populated on an earlier turn of the same thread; this stands in
    for that rather than re-testing profile loading, which is ``test_load_user_context.py``'s
    job.
    """
    state = initial_state(QUESTION, USER_ID) | {
        "profile": PROFILE.model_dump(mode="json")
    }
    return await graph.ainvoke(state, CONFIG)


async def test_both_parts_of_the_request_are_resolved(loop) -> None:
    """The QA half gets an answer, and the coaching half gets a plan staged for approval."""
    result = await _ask(loop)

    assert result["qa_answer"] == ANSWER
    assert result["pending_approval"]["source"] == "coach_agent"
    assert result["pending_approval"]["kind"] == "plan"


async def test_the_qa_agent_runs_before_the_coach_agent(loop) -> None:
    """Resolving the read-only half first is what keeps a later interrupt from splitting it off."""
    await _ask(loop)

    assert loop.supervisor.order == ["qa_agent", "coach_agent"]


async def test_each_agent_runs_exactly_once(loop) -> None:
    """One compound turn, one pass through each agent — not a retry of either."""
    await _ask(loop)

    assert loop.qa_agent.calls == 1
    assert loop.coach_agent.calls == 1


async def test_the_run_suspends_at_the_plan_approval_rather_than_finishing(
    loop,
) -> None:
    """A plan is never final on its own — the turn has to stop for the user's approval."""
    await _ask(loop)

    assert (await loop.aget_state(CONFIG)).next == ("plan_approval",)


async def test_the_answer_reaches_the_transcript_before_the_plan_is_presented(
    loop,
) -> None:
    """The user should see the QA answer land before the plan review starts, not after."""
    result = await _ask(loop)

    contents = [
        message.content
        for message in result["messages"]
        if isinstance(message, AIMessage) and isinstance(message.content, str)
    ]
    answer_index = contents.index(ANSWER)
    plan_index = next(i for i, c in enumerate(contents) if "training plan" in c.lower())

    assert answer_index < plan_index
