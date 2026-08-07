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
from langchain.agents.middleware import AgentState
from langchain_core.messages import AIMessage, HumanMessage, ToolMessage
from langgraph.checkpoint.memory import MemorySaver
from langgraph.graph import StateGraph
from langgraph.types import Command

from app.core.langgraph.agents import AGENTS
from app.core.langgraph.graph import LangGraphAgent, _add_nodes
from app.core.langgraph.routing.dispatch import DISPATCH_TARGETS
from app.schemas.graph import Intent, IntentDecision, Issue, RootState, accumulate_issues
from tests.conftest import FakeChatModel, stub_qa_model


def _config() -> dict:
    """Return a runnable config with a unique thread id."""
    return {"configurable": {"thread_id": str(uuid.uuid4())}}


# Records QA-agent LLM calls so a test can assert which branch ran.
_QA_CALLS: list[str] = []


class _FakeLLM:
    """Stand-in for the shared llm_service, isolated per module.

    ``llm_service`` is a singleton, so patching ``llm_service.call`` through two
    different module paths mutates the *same object* and the second patch wins.
    Replacing the module-level name instead gives each caller its own stub.
    """

    def __init__(self, on_call=None) -> None:
        self._on_call = on_call

    def bind_tools(self, _tools):
        """No-op: nothing binds tools through the service any more."""
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
    """Replace every LLM entry point so no test in this file reaches the network.

    The QA agent is stubbed at its model rather than at ``llm_service``: it
    holds a chat model of its own, which is also what lets these tests tell its
    calls apart from the planner's.
    """
    _QA_CALLS.clear()

    stub_qa_model(monkeypatch, FakeChatModel(on_call=lambda: _QA_CALLS.append("qa"), calls=[]))
    for module in (
        "app.core.langgraph.agents.planning.nodes",
        "app.core.langgraph.profile.nodes",
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
    #
    # Patched on ``graph`` rather than on ``profile.nodes``: ``_add_nodes``
    # registers the name it imported, and looks it up when it runs, so this is
    # the binding that ends up in the compiled graph. The fake skips straight to
    # ``intent_branch``, which the real ``load_profile`` may not do — that is the
    # point of a stub, and why the assertion about the gate lives elsewhere.
    async def fake_load_profile(state, config):
        return Command(update={"profile": _COMPLETE_PROFILE}, goto="intent_branch")

    monkeypatch.setattr("app.core.langgraph.graph.load_profile", fake_load_profile)

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


def test_the_qa_agent_cannot_hold_a_plan():
    """workflow.md 9.4: a knowledge question must not be able to mutate the plan.

    Enforced by the state schema, not by review: there is no field on
    ``QAState`` a plan could be written into. The plan arrives as
    ``plan_context``, rendered text the agent can read and nothing more.
    """
    from app.core.langgraph.agents.qa import QAState

    added = set(QAState.__annotations__) - set(AgentState.__annotations__)
    assert added == {"plan_context", "long_term_memory"}


def test_verify_isolation_fields_have_reducers():
    """workflow.md 12: fan-out fields need a reducer; single-writer fields must not."""
    issues_field = RootState.model_fields["issues"]
    assert issues_field.metadata, "issues is written by three branches concurrently"

    for name in ("draft_plan", "verdict", "computed_macros", "repair_count"):
        assert not RootState.model_fields[name].metadata, (
            f"{name} is written by one branch — a reducer would mask a lost update"
        )


def test_the_qa_agent_is_declared_not_assembled():
    """The agent is a model, a tool and a prompt — no hand-written nodes.

    Asserting the shape keeps the package honest: a `nodes.py` reappearing here
    means someone rebuilt the loop `create_agent` already provides.
    """
    from pathlib import Path

    from app.core.langgraph.agents.qa import build_qa_agent

    package = Path(__file__).resolve().parent.parent / "app/core/langgraph/agents/qa"
    assert {path.name for path in package.glob("*.py")} == {
        "__init__.py",
        "graph.py",
        "state.py",
    }

    agent = build_qa_agent()
    assert agent.name == "qa"
    assert {"model", "tools"} <= set(agent.get_graph().nodes)


async def test_the_qa_agent_stops_searching_after_the_cap(monkeypatch):
    """A model that searches every turn must still end the turn.

    `ToolCallLimitMiddleware` is what stops it. Without a cap the only backstop
    is `recursion_limit`, which ends the turn in an exception rather than an
    answer — the user asked a question and would get a stack trace.
    """
    from app.core.langgraph.agents.qa import build_qa_agent
    from app.core.langgraph.agents.qa.graph import _MAX_SEARCHES

    def _search(index: int) -> AIMessage:
        return AIMessage(
            content="",
            tool_calls=[
                {"name": "search_knowledge", "args": {"query": "creatine"}, "id": f"c{index}"}
            ],
        )

    fake = FakeChatModel(responses=[_search(i) for i in range(_MAX_SEARCHES + 3)], calls=[])
    stub_qa_model(monkeypatch, fake)

    async def no_passages(_query, top_k=4):
        return []

    monkeypatch.setattr("app.services.knowledge.knowledge_service.search", no_passages)

    result = await build_qa_agent().ainvoke(
        {
            "messages": [HumanMessage(content="is creatine worth it?")],
            "plan_context": "",
            "long_term_memory": "",
        }
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


async def test_the_qa_agent_keeps_tool_calls_intact_across_rounds(monkeypatch):
    """The follow-up call must carry real messages, not flattened dicts.

    ``dump_messages`` renders a message as ``{role, content}``, which drops
    ``tool_calls`` from the assistant turn and ``tool_call_id`` from the result;
    the provider rejects that pair. While QA drove its own loop through
    ``llm_service`` it hit exactly that, so every question that did trigger a
    search fell through to the apology. The agent passes message objects.
    """
    fake = FakeChatModel(
        responses=[
            AIMessage(
                content="",
                tool_calls=[
                    {"name": "search_knowledge", "args": {"query": "creatine"}, "id": "c1"}
                ],
            ),
            AIMessage(content="Yes, 3-5 g a day."),
        ],
        calls=[],
    )
    stub_qa_model(monkeypatch, fake)

    async def no_passages(_query, top_k=4):
        return []

    monkeypatch.setattr("app.services.knowledge.knowledge_service.search", no_passages)

    from app.core.langgraph.agents.qa import build_qa_agent

    result = await build_qa_agent().ainvoke(
        {
            "messages": [HumanMessage(content="creatine?")],
            "plan_context": "",
            "long_term_memory": "",
        }
    )

    assert result["messages"][-1].content == "Yes, 3-5 g a day."
    follow_up = fake.calls[1]
    assert any(getattr(m, "tool_calls", None) for m in follow_up), "tool_calls were dropped"
    assert any(isinstance(m, ToolMessage) and m.tool_call_id == "c1" for m in follow_up)


def test_no_write_intent_can_skip_the_profile_gate():
    """The gate is three root nodes now, so its unskippability must be asserted.

    While ``load_profile``, ``extract_profile`` and ``check_required`` lived in a
    subgraph, "every write intent passes the gate" was one edge:
    ``dispatch -> profile_gate``. Lifted to the root graph it is a chain, and a
    later edit could wire ``dispatch`` or an early node straight to
    ``intent_branch`` without anything failing. That is what this test catches
    (``docs/workflow.md`` §1.2, §9.1).
    """
    builder = StateGraph(RootState)
    _add_nodes(builder, LangGraphAgent())
    builder.set_entry_point("classify")
    graph = builder.compile(checkpointer=MemorySaver(), name="root-test")

    # Every intent that can write enters at the top of the gate.
    write_intents = set(Intent.__args__) - {"general_qa"}
    assert {DISPATCH_TARGETS[intent] for intent in write_intents} == {"load_profile"}

    # And only the last node of the gate opens onto the branches.
    reaches_intent_branch = {
        edge.source for edge in graph.get_graph().edges if edge.target == "intent_branch"
    }
    assert reaches_intent_branch == {"check_required"}


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


# ---------------------------------------------------------------------------
# The turn boundary
# ---------------------------------------------------------------------------


def _stale_issue() -> Issue:
    """A finding left behind by an earlier turn."""
    return Issue(
        source="volume",
        severity="warn",
        location="Upper A / vertical push",
        message="No vertical push exercise matches your equipment.",
        suggestion=None,
        rubric_ref="catalog.no_candidates",
    )


def test_the_issues_reducer_only_clears_on_an_explicit_signal():
    """`[]` is a verifier finding nothing; `None` is a new turn starting.

    Conflating them breaks one of two ways: treat `[]` as a clear and the
    volume verifier erases what the injury verifier found beside it; offer no
    clear at all and findings pile up across turns forever.
    """
    first, second = _stale_issue(), _stale_issue()

    assert accumulate_issues([first], [second]) == [first, second]
    assert accumulate_issues([first], []) == [first]
    assert accumulate_issues([first], None) == []


async def test_a_new_turn_does_not_inherit_the_last_one(monkeypatch):
    """The findings of one turn must not be reported as the next turn's.

    State survives in the checkpointer, so without a reset a "make it 5 days"
    turn is answered with the *build's* findings — which name the days of the
    split it just replaced — and, on any branch that produces no plan, with the
    build's plan as well.
    """
    graph = await _build_test_graph(
        monkeypatch, IntentDecision(intent="general_qa", scope=[], changes={})
    )
    config = _config()

    await graph.ainvoke(
        {
            "messages": [{"role": "user", "content": "what is RIR?"}],
            "issues": [_stale_issue()],
            "verdict": "warn",
            "repair_count": 2,
            "draft_plan": {"template_id": "upper_lower_4day", "days": []},
            "computed_macros": {"kcal": 2203, "goal": "muscle_gain"},
            "submitted_plan": {"days": []},
        },
        config,
    )

    values = (await graph.aget_state(config)).values
    assert values["issues"] == []
    assert values["verdict"] is None
    assert values["repair_count"] == 0, "the turn started without its full repair budget"
    assert values["draft_plan"] is None
    assert values["computed_macros"] is None
    assert values["submitted_plan"] is None


async def test_the_approved_plan_survives_the_turn_boundary(monkeypatch):
    """The reset clears what a turn derives, never what the user has.

    The counterpart to the test above, and the reason `NEW_TURN` is a listed
    constant rather than "clear everything": `plan` and `macros` are the plan
    the user follows, and a turn that asks a question must not delete them.
    """
    plan = {"template_id": "upper_lower_4day", "days": [{"name": "Upper A", "exercises": []}]}
    graph = await _build_test_graph(
        monkeypatch, IntentDecision(intent="general_qa", scope=[], changes={})
    )
    config = _config()

    await graph.ainvoke(
        {
            "messages": [{"role": "user", "content": "what is RIR?"}],
            "plan": plan,
            "macros": {"kcal": 2203},
            "current_version_id": "v-old",
        },
        config,
    )

    values = (await graph.aget_state(config)).values
    assert values["plan"] == plan
    assert values["macros"] == {"kcal": 2203}
    assert values["current_version_id"] == "v-old"
