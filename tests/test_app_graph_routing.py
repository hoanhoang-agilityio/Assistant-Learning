"""Routing tests for the app/ root graph.

The property worth regression-testing is that mandatory steps cannot be
bypassed: every intent goes through ``classify`` then ``dispatch``, and only
``general_qa`` reaches the QA agent. Assertions are on state transitions and the
structured routing decision — never on prose, which changes with every prompt
edit.

No HTTP and no Postgres: the graph is compiled with ``MemorySaver`` and the LLM
boundary is stubbed.
"""

import uuid

import pytest
from langchain_core.messages import AIMessage
from langgraph.checkpoint.memory import MemorySaver
from langgraph.graph import StateGraph
from langgraph.types import Command

from app.core.langgraph.agents import AGENTS
from app.core.langgraph.agents.qa.graph import build_qa_graph
from app.core.langgraph.graph import LangGraphAgent, _add_nodes
from app.core.langgraph.routing.dispatch import DISPATCH_TARGETS
from app.schemas.graph import Intent, IntentDecision, RootState


def _config() -> dict:
    """Return a runnable config with a unique thread id."""
    return {"configurable": {"thread_id": str(uuid.uuid4())}}


# Records QA-agent LLM calls so a test can assert which branch ran.
_QA_CALLS: list[str] = []


class _FakeLLM:
    """Stand-in for the shared llm_service, isolated per module.

    ``llm_service`` is a singleton, so patching ``llm_service.call`` through two
    different module paths mutates the *same object* and the second patch wins.
    Replacing the module-level name instead gives each caller its own stub,
    which is the only way to tell the QA agent's calls from the planner's.
    """

    def __init__(self, on_call=None) -> None:
        self._on_call = on_call

    def bind_tools(self, _tools):
        """No-op: LangGraphAgent binds tools at construction."""
        return self

    async def call(self, _messages, *_args, **kwargs):
        if self._on_call:
            self._on_call()
        response_format = kwargs.get("response_format")
        if response_format is not None:
            return response_format()
        return AIMessage(content="an answer")


@pytest.fixture(autouse=True)
def _stub_every_llm_boundary(monkeypatch):
    """Replace every LLM entry point so no test in this file reaches the network."""
    _QA_CALLS.clear()

    monkeypatch.setattr(
        "app.core.langgraph.agents.qa.nodes.llm_service",
        _FakeLLM(on_call=lambda: _QA_CALLS.append("qa")),
    )
    for module in (
        "app.core.langgraph.agents.planning.nodes",
        "app.core.langgraph.agents.profile.nodes",
        "app.core.langgraph.agents.ingest.nodes",
        "app.core.langgraph.graph",
    ):
        monkeypatch.setattr(f"{module}.llm_service", _FakeLLM())

    async def no_snapshot(**_kwargs):
        return {"version_id": "v", "label": "v1", "created_at": "2026-01-01T00:00:00"}

    async def no_index(_user_id):
        return []

    monkeypatch.setattr("app.core.langgraph.graph.insert_version", no_snapshot)
    monkeypatch.setattr("app.core.langgraph.graph.version_index", no_index)


async def _build_test_graph(monkeypatch, decision: IntentDecision):
    """Compile the root graph with an in-memory checkpointer and a stub classifier.

    Args:
        monkeypatch: pytest fixture used to replace the LLM boundary.
        decision: What the stubbed classifier should return.

    Returns:
        The compiled graph.
    """

    async def fake_llm_classify(_conversation: str) -> IntentDecision:
        return decision

    monkeypatch.setattr("app.core.langgraph.routing.classify.llm_classify", fake_llm_classify)

    agent = LangGraphAgent()
    agent._agents = {name: build() for name, build in AGENTS.items()}

    # The profile gate is stubbed to "everything present" so these tests stay
    # about routing. Whether the gate itself blocks correctly is
    # tests/test_app_root_pipeline.py's job.
    async def fake_profile_gate(state, config):
        return Command(update={"profile": _COMPLETE_PROFILE}, goto="intent_branch")

    agent._profile_gate = fake_profile_gate

    builder = StateGraph(RootState)
    # Built through the same helper the real graph uses, so a topology change
    # cannot leave these tests asserting against a shape that no longer exists.
    _add_nodes(builder, agent)
    builder.set_entry_point("classify")
    return builder.compile(checkpointer=MemorySaver(), name="root-test")


_COMPLETE_PROFILE = {
    "weight_kg": 75.0,
    "height_cm": 175.0,
    "age": 28,
    "sex": "male",
    "activity_level": "light",
    "days_per_week": 4,
    "level": 3,
    "goal": "fat_loss",
    "equipment": ["barbell", "cable", "dumbbell", "machine", "bodyweight"],
    "injuries": [],
    "preferences": "",
}


def test_every_intent_has_a_dispatch_target():
    """A new Intent literal without a target here would silently fall back."""
    assert set(DISPATCH_TARGETS) == set(Intent.__args__)


def test_qa_state_cannot_hold_a_plan():
    """workflow.md 9.4: a knowledge question must not be able to mutate the plan."""
    from app.core.langgraph.agents.qa.state import QAState

    assert set(QAState.__annotations__) == {
        "messages",
        "plan_context",
        "long_term_memory",
        "answer",
    }


def test_verify_isolation_fields_have_reducers():
    """workflow.md 12: fan-out fields need a reducer; single-writer fields must not."""
    issues_field = RootState.model_fields["issues"]
    assert issues_field.metadata, "issues is written by three branches concurrently"

    for name in ("draft_plan", "verdict", "computed_macros", "repair_count"):
        assert not RootState.model_fields[name].metadata, (
            f"{name} is written by one branch — a reducer would mask a lost update"
        )


def test_qa_subgraph_compiles_standalone():
    """The QA agent must build without the root graph or a checkpointer."""
    graph = build_qa_graph()
    assert graph.name == "qa"
    assert {"answer_qa", "tool_call"} <= set(graph.get_graph().nodes)


def test_only_finalize_ends_the_graph():
    """A terminal branch wired straight to END would drop its reply from history.

    ``answer`` is returned to the caller; ``messages`` is what the checkpointer
    replays on the next visit. Only ``finalize`` copies one into the other, so a
    branch that bypasses it produces a conversation that reloads as the user
    talking to themselves.
    """
    builder = StateGraph(RootState)
    _add_nodes(builder, LangGraphAgent())
    builder.set_entry_point("classify")
    graph = builder.compile(checkpointer=MemorySaver(), name="root-test")

    ends_at = {edge.source for edge in graph.get_graph().edges if edge.target.endswith("__end__")}
    assert ends_at == {"finalize"}


@pytest.mark.parametrize(
    ("intent", "reaches_qa"),
    [
        ("general_qa", True),
        ("build_plan", False),
        ("change_plan", False),
        ("check", False),
        ("revert", False),
    ],
)
async def test_only_general_qa_reaches_the_qa_agent(monkeypatch, intent, reaches_qa):
    """Every write intent goes through the profile gate, never to the QA agent.

    The failure this prevents is a plan request being answered conversationally:
    the QA model would produce a plausible plan with invented sets and reps,
    which is exactly what §1.1 exists to stop.
    """
    visited = _QA_CALLS

    graph = await _build_test_graph(
        monkeypatch, IntentDecision(intent=intent, scope=[], changes={})
    )
    config = _config()
    await graph.ainvoke({"messages": [{"role": "user", "content": "hello"}]}, config)

    state = await graph.aget_state(config)
    assert state.values["intent"] == intent
    assert bool(visited) is reaches_qa
    assert state.values["answer"]

    # The reply has to survive in `messages`, not just in `answer`: that is what
    # GET /chatbot/messages reads and what the next turn replays. Exactly once —
    # the QA branch already carries its own AIMessage back.
    recorded = [
        message
        for message in state.values["messages"]
        if isinstance(message, AIMessage) and message.content == state.values["answer"]
    ]
    assert len(recorded) == 1


async def test_scope_is_dropped_for_non_check_intents(monkeypatch):
    """Only `check` lets the classifier choose verifiers; other intents get none."""
    graph = await _build_test_graph(
        monkeypatch,
        IntentDecision(intent="build_plan", scope=["macro", "volume"], changes={"days": 5}),
    )
    config = _config()
    await graph.ainvoke({"messages": [{"role": "user", "content": "make me a plan"}]}, config)

    state = await graph.aget_state(config)
    assert state.values["scope"] == []
    assert state.values["changes"] == {}


async def test_check_intent_keeps_its_scope(monkeypatch):
    """A `check` turn must carry the verifier selection through to dispatch."""
    graph = await _build_test_graph(
        monkeypatch,
        IntentDecision(intent="check", scope=["injury"], changes={}),
    )
    config = _config()
    await graph.ainvoke({"messages": [{"role": "user", "content": "my knee hurts"}]}, config)

    state = await graph.aget_state(config)
    assert state.values["scope"] == ["injury"]


async def test_classifier_failure_falls_back_to_qa(monkeypatch):
    """A classifier error must not route a turn onto a plan-writing branch."""

    async def exploding_classify(_conversation: str) -> IntentDecision:
        raise RuntimeError("model unavailable")

    monkeypatch.setattr("app.core.langgraph.routing.classify.llm_classify", exploding_classify)

    graph = await _build_test_graph(
        monkeypatch, IntentDecision(intent="general_qa", scope=[], changes={})
    )

    config = _config()
    await graph.ainvoke({"messages": [{"role": "user", "content": "hi"}]}, config)

    state = await graph.aget_state(config)
    assert state.values["intent"] == "general_qa"
    assert state.values["answer"] == "an answer"
