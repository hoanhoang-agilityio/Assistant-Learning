"""Tests for the supervisor, and for the guarantees the conversion had to move.

The old root graph proved three of its properties by reading edges:
``test_no_intent_can_skip_the_profile_gate``, ``test_only_finalize_ends_the_graph``,
``test_decline_cannot_reach_anything_that_touches_a_plan``. None of those port —
there are no edges left to read. Their replacements are of two kinds, and
``docs/supervisor-architecture.md`` §11.2 is explicit that the first is stronger
than the second:

**Static.** No subagent's tool set contains a write tool; ``save_plan``'s
signature has no ``plan`` parameter; every plan-producing tool routes through
``commit_draft``; every envelope carrying a ``draft_id`` carries macros. All four
are checkable without running a model, which is what makes them worth more than
the behaviour tests below.

**Behavioural.** The topic gate, the profile precondition, the confirm gate and
the save refusal are exercised with a scripted model. Slower and weaker than an
edge, and the honest price of the architecture.
"""

import inspect
import json
import uuid

import pytest
from langchain_core.messages import AIMessage, HumanMessage
from langgraph.checkpoint.memory import MemorySaver

from app.core.langgraph.agents.planning import tools as planning_tools
from app.core.langgraph.agents.qa import QAState
from app.core.langgraph.agents.review import tools as review_tools
from app.core.langgraph.runtime import draft_store as drafts
from app.core.langgraph.runtime.facade import DECLINED_MESSAGE, _is_affirmative
from app.core.langgraph.supervisor import WRITE_TOOLS, SupervisorState, build_supervisor_with
from app.core.langgraph.supervisor import tools as supervisor_tools
from app.core.langgraph.supervisor.middleware import OFF_TOPIC_ANSWER
from app.core.langgraph.supervisor.state import NEW_TURN
from app.schemas.graph import IntentDecision
from tests.conftest import FakeChatModel, reset_agents, stub_model, tool_call
from tests.support import call, message, updates

PROFILE = {
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

PLAN = {
    "template_id": "upper_lower_4day",
    "days": [
        {
            "name": "Upper A",
            "exercises": [
                {
                    "slot_id": "s0",
                    "exercise_id": "back_squat",
                    "name": "Back Squat",
                    "sets": 4,
                    "reps": [5, 8],
                    "rir": [1, 2],
                }
            ],
        }
    ],
}

MACROS = {"kcal": 2100, "tdee": 2400, "goal": "fat_loss", "protein_g": 150}


def _state(**overrides) -> SupervisorState:
    """Build a supervisor state the tools can read."""
    return {
        "messages": [],
        "profile": dict(PROFILE),
        "plan": None,
        "macros": None,
        "episodic_context": "",
        "current_version_id": None,
        "intent_hint": None,
        "missing_fields": [],
        "goal_conflict": None,
        **overrides,
    }


def _config(user_id: str | None = "1") -> dict:
    """A runnable config with a unique thread id and an owner."""
    return {
        "configurable": {"thread_id": str(uuid.uuid4())},
        "metadata": {"user_id": user_id, "session_id": "s-1"},
    }


def _draft(verdict: str = "pass", **overrides) -> drafts.Draft:
    """Mint a draft directly, standing in for one ``commit_draft`` produced."""
    return drafts.mint(
        plan=dict(PLAN),
        macros=dict(MACROS),
        issues=overrides.pop("issues", []),
        verdict=verdict,
        plan_rendered="Split: Upper / Lower\nSessions a week: 1",
        profile_hash="hash",
        rubric_version="v1",
        **overrides,
    )


# ---------------------------------------------------------------------------
# Static substitutes for the topology proofs (§11.2)
# ---------------------------------------------------------------------------


def test_no_subagent_can_reach_a_write_tool():
    """The only write in the system lives at supervisor level and nowhere else.

    Replaces ``test_decline_cannot_reach_anything_that_touches_a_plan``, which
    proved the same thing by showing the decline node had no edge to a plan node.
    """
    for module in (planning_tools, review_tools):
        names = {tool.name for tool in module.tools}
        assert not names & WRITE_TOOLS, f"{module.__name__} exposes a write tool"

    assert WRITE_TOOLS <= {tool.name for tool in supervisor_tools.tools}


def test_save_plan_has_no_plan_parameter():
    """The content comes from the draft store, so there is nothing to retype.

    A ``plan`` parameter would let a model hand over numbers of its own on the
    way to ``plan_versions``, which is the one substitution the draft store
    exists to make impossible.
    """
    parameters = set(
        inspect.signature(
            supervisor_tools.save_plan.func or supervisor_tools.save_plan.coroutine
        ).parameters
    )
    assert parameters == {"draft_id", "runtime"}


def test_no_plan_producing_tool_accepts_a_profile():
    """A tool that took one would let the model invent a weight for the user."""
    for tool in supervisor_tools.tools:
        parameters = set(inspect.signature(tool.coroutine or tool.func).parameters)
        assert "profile" not in parameters, f"{tool.name} accepts a profile"


def test_only_commit_draft_mints_a_handle():
    """Every plan the system will save routes through one function. §11.1."""
    minting: list[str] = []
    for module in (planning_tools, review_tools, supervisor_tools):
        for tool in module.tools:
            if "drafts.mint" in inspect.getsource(tool.coroutine or tool.func):
                minting.append(tool.name)

    # `restore_version` mints too, and must: a restored plan is re-verified
    # against the profile as it stands now, which is a new draft rather than the
    # old one revived.
    assert sorted(minting) == ["commit_draft", "restore_version"]


def test_every_minted_draft_carries_macros():
    """The invariant that replaces ``calc_macro``'s position in the topology.

    Nothing may reach the draft store without having been scored, so ``mint``
    is asserted to be unreachable without macros — and both of its callers to
    obtain them from :func:`app.core.langgraph.verification.scoring.score`.
    """
    signature = inspect.signature(drafts.mint)
    for required in ("macros", "verdict", "issues"):
        assert signature.parameters[required].default is inspect.Parameter.empty

    for tool in (planning_tools.commit_draft, supervisor_tools.restore_version):
        source = inspect.getsource(tool.coroutine or tool.func)
        assert "await score(" in source, f"{tool.name} mints a draft without scoring it"


def test_the_verifier_still_has_nowhere_to_put_a_transcript():
    """Blind rubric scoring, and now more strongly than before.

    ``VerifyState`` used to enforce this by omitting ``messages``. With the
    subgraph gone the guarantee is in the signatures: neither :func:`score` nor
    the checks it calls take an argument a transcript could arrive in.
    """
    from app.core.langgraph.verification import scoring

    verifiers = (
        scoring.score,
        scoring.run_checks,
        scoring.verify_macro,
        scoring.verify_volume,
        scoring.verify_injury,
    )
    for function in verifiers:
        assert "messages" not in inspect.signature(function).parameters

    assert "messages" not in inspect.getsource(scoring)


def test_the_qa_agent_still_cannot_hold_a_plan():
    """A knowledge question must not be able to mutate the plan.

    ``profile`` was added for ``estimate_macros``, which needs numbers rather
    than prose. It is read-only in the same sense the rest is: there is still no
    field a plan or a saved target could be written into.
    """
    from langchain.agents.middleware import AgentState

    added = set(QAState.__annotations__) - set(AgentState.__annotations__)
    assert added == {"plan_context", "episodic_context", "profile"}


def test_estimate_macros_is_qa_only():
    """Safe there because QA is read-only; unsafe anywhere with a path to a save."""
    from app.core.langgraph.agents.qa.agent import tools as qa_tools

    assert "estimate_macros" in {tool.name for tool in qa_tools}
    for module in (planning_tools, review_tools, supervisor_tools):
        assert "estimate_macros" not in {tool.name for tool in module.tools}


# ---------------------------------------------------------------------------
# The profile precondition (§10)
# ---------------------------------------------------------------------------


async def test_an_incomplete_profile_refuses_and_names_every_missing_field():
    """Calling the tool anyway achieves nothing but a list of what to ask for."""
    result = await call(
        supervisor_tools.planning_agent, _state(profile={"weight_kg": 75.0}), _config()
    )
    body = json.loads(message(result).content)

    assert body["status"] == "missing_fields"
    assert "activity_level" in body["fields"]
    assert body["ask_for"], "the refusal must carry wording the supervisor can ask with"
    assert message(result).status == "error"
    assert updates(result)["missing_fields"] == body["fields"]


async def test_a_contradicted_goal_refuses_rather_than_picking_one():
    """It flips the calorie target from a deficit to a surplus, so it asks."""
    conflict = {"stored": "muscle_gain", "implied": "fat_loss"}
    result = await call(
        supervisor_tools.planning_agent,
        _state(profile={**PROFILE, "goal": "muscle_gain"}, goal_conflict=conflict),
        _config(),
    )
    body = json.loads(message(result).content)

    assert body["status"] == "refused"
    assert "muscle gain" in body["reason"]
    assert "fat loss" in body["reason"]


async def test_a_review_is_not_blocked_by_programme_fields():
    """Scoring a pasted plan needs body data, not the shape of a programme."""
    body_only = {
        key: PROFILE[key]
        for key in ("weight_kg", "height_cm", "age", "sex", "activity_level", "injuries")
    }
    result = await call(
        supervisor_tools.review_agent, _state(profile=body_only), _config(), pasted="squats 3x5"
    )
    assert json.loads(message(result).content)["status"] != "missing_fields"


async def test_changing_a_plan_that_does_not_exist_is_refused():
    """ "Make it 5 days" with nothing saved is a mistake worth naming."""
    result = await call(
        supervisor_tools.planning_agent, _state(plan=None), _config(), mode="change"
    )
    body = json.loads(message(result).content)

    assert body["status"] == "refused"
    assert "no saved plan" in body["reason"]


# ---------------------------------------------------------------------------
# Saving (§9, rules 2 and 3)
# ---------------------------------------------------------------------------


async def test_save_reads_the_plan_from_the_store_not_from_the_model(monkeypatch):
    """What is written is what was verified."""
    drafts.clear()
    written: list[dict] = []

    async def fake_insert(**kwargs):
        written.append(kwargs)
        return {"version_id": "v-1", "label": "v1", "created_at": "2026-08-10T00:00:00"}

    monkeypatch.setattr(
        "app.core.langgraph.supervisor.tools.persistence.insert_version", fake_insert
    )

    draft = _draft()
    result = await call(supervisor_tools.save_plan, _state(), _config(), draft_id=draft.draft_id)

    assert json.loads(message(result).content)["status"] == "saved"
    assert written[0]["plan"] == PLAN
    assert written[0]["macros"] == MACROS
    assert written[0]["profile_hash"] == "hash", "the hash the verdict was produced under"
    assert updates(result) == {"plan": PLAN, "macros": MACROS, "current_version_id": "v-1"}


async def test_a_failing_draft_is_refused_at_save_time(monkeypatch):
    """Rule 3: a failing plan that reaches the store is a failing plan someone trains."""
    drafts.clear()

    async def fail(**_kwargs):
        raise AssertionError("a failing draft was written to plan_versions")

    monkeypatch.setattr("app.core.langgraph.supervisor.tools.persistence.insert_version", fail)

    draft = _draft(
        verdict="fail",
        issues=[
            {
                "source": "volume",
                "severity": "block",
                "location": "Upper A",
                "message": "Weekly chest volume is above MRV.",
                "suggestion": None,
                "rubric_ref": "volume.mrv",
            }
        ],
    )
    result = await call(supervisor_tools.save_plan, _state(), _config(), draft_id=draft.draft_id)
    body = json.loads(message(result).content)

    assert body["status"] == "refused"
    assert "above MRV" in body["reason"]
    assert "plan" not in updates(result)


async def test_an_expired_handle_is_refused_rather_than_guessed():
    """Rule 4: a stale draft describes a profile that may have changed since."""
    drafts.clear()
    result = await call(supervisor_tools.save_plan, _state(), _config(), draft_id="gone")
    body = json.loads(message(result).content)

    assert body["status"] == "refused"
    assert "expired" in body["reason"]


async def test_a_saved_draft_cannot_be_saved_twice(monkeypatch):
    """Two versions with the same content is a history the user cannot read."""
    drafts.clear()

    async def fake_insert(**_kwargs):
        return {"version_id": "v-1", "label": "v1", "created_at": "2026-08-10T00:00:00"}

    monkeypatch.setattr(
        "app.core.langgraph.supervisor.tools.persistence.insert_version", fake_insert
    )

    draft = _draft()
    await call(supervisor_tools.save_plan, _state(), _config(), draft_id=draft.draft_id)
    again = await call(supervisor_tools.save_plan, _state(), _config(), draft_id=draft.draft_id)

    assert json.loads(message(again).content)["status"] == "refused"


async def test_an_anonymous_session_keeps_the_plan_without_a_row(monkeypatch):
    """There is no user to own the row, but the conversation still has a plan."""
    drafts.clear()

    async def fail(**_kwargs):
        raise AssertionError("a version was written for an anonymous session")

    monkeypatch.setattr("app.core.langgraph.supervisor.tools.persistence.insert_version", fail)

    draft = _draft()
    result = await call(
        supervisor_tools.save_plan, _state(), _config(user_id=None), draft_id=draft.draft_id
    )

    assert updates(result)["plan"] == PLAN
    assert json.loads(message(result).content)["version_id"] == ""


# ---------------------------------------------------------------------------
# The topic gate (§4.3)
# ---------------------------------------------------------------------------


@pytest.fixture
def supervisor(monkeypatch):
    """Build the supervisor with every boundary but the model stubbed.

    Returns a factory taking the scripted model responses and the intent the
    classifier should return, and giving back ``(graph, config, fake)``.
    """

    async def fake_get_profile(_user_id):
        return dict(PROFILE)

    async def fake_latest_version(_user_id):
        return None

    async def fake_recent_episodes(_user_id, _session_id):
        return ""

    async def fake_upsert(_user_id, _profile):
        return None

    monkeypatch.setattr(
        "app.core.langgraph.supervisor.middleware.profile_service.get_profile", fake_get_profile
    )
    monkeypatch.setattr(
        "app.core.langgraph.supervisor.middleware.profile_service.upsert_profile", fake_upsert
    )
    monkeypatch.setattr(
        "app.core.langgraph.supervisor.middleware.latest_version", fake_latest_version
    )
    monkeypatch.setattr(
        "app.core.langgraph.supervisor.middleware.recent_episodes", fake_recent_episodes
    )

    def _build(responses: list[AIMessage], intent: str = "build_plan"):
        classified: list[str] = []

        async def fake_classify(conversation):
            classified.append(conversation)
            return IntentDecision(intent=intent, scope=[], changes={})

        extracted: list[str] = []

        async def fake_extract(*_args, **_kwargs):
            extracted.append("called")
            from app.schemas.graph import ProfileExtraction

            return ProfileExtraction()

        monkeypatch.setattr("app.core.langgraph.supervisor.middleware.llm_classify", fake_classify)

        class _FakeLLM:
            async def call(self, _messages, *_a, **_kw):
                return await fake_extract()

        monkeypatch.setattr("app.core.langgraph.supervisor.middleware.llm_service", _FakeLLM())

        reset_agents()
        fake = stub_model(monkeypatch, FakeChatModel(responses=responses, calls=[]))
        graph = build_supervisor_with(MemorySaver())
        return graph, _config(), fake, {"classified": classified, "extracted": extracted}

    return _build


async def test_an_off_topic_turn_never_enters_the_loop(supervisor):
    """The refusal is a constant, and the model is never handed the message."""
    graph, config, fake, seen = supervisor(
        [AIMessage(content="should not run")], intent="off_topic"
    )

    result = await graph.ainvoke(
        {"messages": [HumanMessage(content="what's the capital of France?")]}, config
    )

    assert result["messages"][-1].content == OFF_TOPIC_ANSWER
    assert fake.calls == [], "the supervisor model was called on an off-topic turn"
    assert seen["extracted"] == [], "an off-topic message was fed to the profile extractor"


async def test_an_on_topic_turn_carries_the_hint_without_being_routed_by_it(supervisor):
    """The hint is advisory: it reaches state, and nothing dispatches on it."""
    graph, config, _fake, _seen = supervisor([AIMessage(content="Here you go.")], intent="check")

    result = await graph.ainvoke({"messages": [HumanMessage(content="review this")]}, config)
    assert result["intent_hint"] == "check"


async def test_a_classifier_failure_does_not_decline(monkeypatch, supervisor):
    """A classifier that just failed has made no decision, least of all a refusal."""
    graph, config, fake, _seen = supervisor([AIMessage(content="Sure.")])

    async def boom(_conversation):
        raise RuntimeError("model unavailable")

    monkeypatch.setattr("app.core.langgraph.supervisor.middleware.llm_classify", boom)

    result = await graph.ainvoke({"messages": [HumanMessage(content="build me a plan")]}, config)

    assert result["messages"][-1].content == "Sure."
    assert result.get("intent_hint") is None
    assert fake.calls, "the turn was declined on an outage"


async def test_the_profile_is_read_once_per_turn_not_once_per_hop(supervisor):
    """Nothing the model does mid-turn changes what the user said."""
    graph, config, _fake, seen = supervisor(
        [
            tool_call("qa_agent", {"question": "what is RIR?"}),
            AIMessage(content="Reps in reserve."),
        ],
        intent="general_qa",
    )

    async def fake_qa(_state, _config=None, **_kw):
        return {"messages": [AIMessage(content="Reps in reserve.")]}

    from app.core.langgraph import agents

    class _Stub:
        async def ainvoke(self, _state, _config=None):
            return {"messages": [AIMessage(content="Reps in reserve.")]}

    agents._built["qa"] = _Stub()
    await graph.ainvoke({"messages": [HumanMessage(content="what is RIR?")]}, config)

    assert len(seen["extracted"]) == 1, "the extractor ran once per model call"
    reset_agents()


# ---------------------------------------------------------------------------
# The confirm gate
# ---------------------------------------------------------------------------


def test_the_turn_reset_keeps_what_the_user_has():
    """Clearing the plan every turn would delete it."""
    for field in ("plan", "macros", "profile", "current_version_id"):
        assert field not in NEW_TURN, f"{field} is what the user has, not what a turn derives"

    assert set(NEW_TURN) == {"missing_fields", "goal_conflict", "intent_hint"}


@pytest.mark.parametrize(
    ("reply", "expected"),
    [
        ("yes", True),
        ("Yes please", True),
        ("ok, do it", True),
        ("no", False),
        ("", False),
        ("what would that change?", False),
        ("yes but can you also make it 6 days and swap the squats out", False),
    ],
)
def test_anything_that_is_not_a_yes_is_a_no(reply, expected):
    """A gate that resolves ambiguity in favour of proceeding is not a gate."""
    assert _is_affirmative(reply) is expected


def test_the_gate_interrupts_on_a_tool_name_not_on_a_judgment():
    """A model cannot reason its way past a name."""
    from app.core.langgraph.supervisor.agent import build_supervisor_with

    graph = build_supervisor_with(None)
    assert "HumanInTheLoopMiddleware.after_model" in set(graph.get_graph().nodes)


def test_the_gate_allows_no_decision_that_could_substitute_a_draft():
    """``edit`` would let the confirm step hand back a different handle."""
    from app.core.langgraph.supervisor.agent import _SAVE_DECISIONS

    assert set(_SAVE_DECISIONS) == {"approve", "reject"}


def test_declining_says_nothing_changed():
    """The one thing a decline must communicate."""
    assert "Nothing has changed" in DECLINED_MESSAGE
