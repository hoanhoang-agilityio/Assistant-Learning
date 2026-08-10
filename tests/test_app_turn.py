"""End-to-end tests for one chat turn, through the facade the API calls.

The whole supervisor, compiled with ``MemorySaver`` and every boundary but the
model stubbed. No Postgres: profile loading, profile saving and version
insertion are patched, so these tests assert turn behaviour rather than storage.

What the old root-pipeline tests proved by walking a spine, these prove by
scripting a model and watching what the turn does with the result. Weaker, and
the honest price of the conversion (``docs/supervisor-architecture.md`` §11.2) —
so the properties chosen are the ones a user would notice going wrong:

* a plan is shown and **not saved** until the user says to keep it
* "yes" saves the plan they were shown, and only that plan
* anything that is not a yes leaves the stored plan exactly as it was
* a fresh session rehydrates the plan the user already has
* the answer the API returns is the one recorded in the transcript
"""

import uuid

import pytest
from langchain_core.messages import AIMessage
from langgraph.checkpoint.memory import MemorySaver

from app.core.langgraph import drafts
from app.core.langgraph.graph import LangGraphAgent
from app.core.langgraph.supervisor import build_supervisor_with
from app.schemas.chat import Message
from app.schemas.graph import IntentDecision, ProfileExtraction
from tests.conftest import FakeChatModel, reset_agents, stub_model, tool_call

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


@pytest.fixture
def turn(monkeypatch):
    """Build the facade over a stubbed supervisor.

    Returns a factory taking the scripted model responses and the stored
    profile, and giving back ``(agent, session_id, calls)`` where ``calls``
    records what each stub saw.
    """
    calls: dict[str, list] = {"versions": [], "saved_profiles": []}

    async def fake_upsert(user_id, profile):
        calls["saved_profiles"].append((user_id, profile))

    async def fake_recent_episodes(_user_id, _session_id):
        return ""

    async def fake_insert_version(**kwargs):
        calls["versions"].append(kwargs)
        return {"version_id": "v-1", "label": "v1", "created_at": "2026-08-10T00:00:00"}

    monkeypatch.setattr(
        "app.core.langgraph.supervisor.middleware.profile_service.upsert_profile", fake_upsert
    )
    monkeypatch.setattr(
        "app.core.langgraph.supervisor.middleware.recent_episodes", fake_recent_episodes
    )
    monkeypatch.setattr("app.core.langgraph.supervisor.tools.insert_version", fake_insert_version)
    monkeypatch.setattr("app.core.langgraph.rendering.load_catalog", lambda *a, **k: {})

    def _build(
        responses: list[AIMessage],
        stored_profile: dict | None = None,
        intent: str = "build_plan",
        saved_plan: dict | None = None,
    ):
        async def fake_get_profile(_user_id):
            return dict(stored_profile if stored_profile is not None else PROFILE)

        async def fake_latest_version(_user_id):
            if saved_plan is None:
                return None
            from types import SimpleNamespace

            return SimpleNamespace(id="v-0", plan=saved_plan, macros=MACROS)

        async def fake_classify(_conversation):
            return IntentDecision(intent=intent, scope=[], changes={})

        class _FakeLLM:
            async def call(self, _messages, *_a, **_kw):
                return ProfileExtraction()

        monkeypatch.setattr(
            "app.core.langgraph.supervisor.middleware.profile_service.get_profile",
            fake_get_profile,
        )
        monkeypatch.setattr(
            "app.core.langgraph.supervisor.middleware.latest_version", fake_latest_version
        )
        monkeypatch.setattr("app.core.langgraph.supervisor.middleware.llm_classify", fake_classify)
        monkeypatch.setattr("app.core.langgraph.supervisor.middleware.llm_service", _FakeLLM())

        reset_agents()
        stub_model(monkeypatch, FakeChatModel(responses=responses, calls=[]))

        agent = LangGraphAgent()
        # Bypasses `create_graph`, which would open a Postgres pool. What is
        # under test is the facade's own work — resume translation, the pending
        # interrupt, reading the answer back — not how it acquires a
        # checkpointer.
        agent._graph = build_supervisor_with(MemorySaver())
        return agent, str(uuid.uuid4()), calls

    return _build


def _user(text: str) -> list[Message]:
    """One user message, as the route would deliver it."""
    return [Message(role="user", content=text)]


@pytest.fixture(autouse=True)
def _a_draft_to_save(monkeypatch):
    """Make the planning tool hand back a fixed draft.

    The planning agent has its own tests. What this module needs from it is a
    handle, so the turn has something real to offer, confirm and save.
    """
    drafts.clear()
    minted: dict[str, str] = {}

    async def fake_planning(runtime, mode="build", changes=None):
        from langchain_core.messages import ToolMessage
        from langgraph.types import Command

        draft = drafts.mint(
            plan=dict(PLAN),
            macros=dict(MACROS),
            issues=[],
            verdict="pass",
            plan_rendered="Split: Upper / Lower\nSessions a week: 1",
            profile_hash="hash",
            rubric_version="v1",
        )
        minted["draft_id"] = draft.draft_id
        return Command(
            update={
                "messages": [
                    ToolMessage(
                        content=f'{{"status": "draft", "draft_id": "{draft.draft_id}"}}',
                        tool_call_id=runtime.tool_call_id,
                    )
                ]
            }
        )

    # Replaced on the tool object itself, not on the module-level name: the
    # supervisor binds its tools at build time, so a patched name would arrive
    # too late to be the thing that runs.
    from app.core.langgraph.supervisor import tools as supervisor_tools

    monkeypatch.setattr(supervisor_tools.planning_agent, "coroutine", fake_planning)
    return minted


# ---------------------------------------------------------------------------
# The confirm gate, end to end
# ---------------------------------------------------------------------------


async def test_a_plan_is_shown_and_not_saved_until_asked(turn, _a_draft_to_save):
    """A build shows the plan; keeping it is the user's next move, not the model's."""
    agent, session, calls = turn(
        [
            tool_call("planning_agent", {"mode": "build"}, "c1"),
            AIMessage(content="Here is a 4-day plan. Want me to keep it?"),
        ]
    )

    answer = await agent.get_response(_user("build me a plan"), session, user_id="1")

    assert "Want me to keep it?" in answer[0].content
    assert calls["versions"] == [], "a build saved a version without being asked"


async def test_saving_stops_for_confirmation(turn, _a_draft_to_save):
    """The gate interrupts on the tool name, before the write runs."""
    agent, session, calls = turn(
        [
            tool_call("planning_agent", {"mode": "build"}, "c1"),
            tool_call("save_plan", {"draft_id": "PLACEHOLDER"}, "c2"),
        ]
    )
    # The handle is only known once the planning tool has run, so the scripted
    # save call is rewritten between the two model turns.
    await _run_until_gate(agent, session, _a_draft_to_save)

    state = await agent._graph.aget_state(_thread(session))
    assert state.tasks and any(task.interrupts for task in state.tasks)
    assert calls["versions"] == [], "a version was written before the user agreed"


async def test_a_yes_saves_the_plan_that_was_shown(turn, _a_draft_to_save):
    """The content comes from the draft, so it is the plan they approved."""
    agent, session, calls = turn(
        [
            tool_call("planning_agent", {"mode": "build"}, "c1"),
            tool_call("save_plan", {"draft_id": "PLACEHOLDER"}, "c2"),
            AIMessage(content="Saved as v1."),
        ]
    )
    await _run_until_gate(agent, session, _a_draft_to_save)

    answer = await agent.get_response(_user("yes"), session, user_id="1")

    assert len(calls["versions"]) == 1
    assert calls["versions"][0]["plan"] == PLAN
    assert calls["versions"][0]["macros"] == MACROS
    assert "Saved" in answer[0].content


async def test_a_no_leaves_the_stored_plan_alone(turn, _a_draft_to_save):
    """Backing out must leave the user exactly where they were."""
    agent, session, calls = turn(
        [
            tool_call("planning_agent", {"mode": "build"}, "c1"),
            tool_call("save_plan", {"draft_id": "PLACEHOLDER"}, "c2"),
            AIMessage(content="Left it as it was."),
        ]
    )
    await _run_until_gate(agent, session, _a_draft_to_save)

    await agent.get_response(_user("actually no"), session, user_id="1")

    assert calls["versions"] == [], "a declined save wrote a version"
    state = await agent._graph.aget_state(_thread(session))
    assert state.values.get("plan") is None, "a declined save changed the held plan"


async def test_the_question_the_user_sees_describes_the_plan(turn, _a_draft_to_save):
    """A confirm question that does not show the plan is not a confirmation."""
    agent, session, _calls = turn(
        [
            tool_call("planning_agent", {"mode": "build"}, "c1"),
            tool_call("save_plan", {"draft_id": "PLACEHOLDER"}, "c2"),
        ]
    )
    answer = await _run_until_gate(agent, session, _a_draft_to_save)

    assert "Sessions a week: 1" in answer[0].content
    assert "until you say yes" in answer[0].content


# ---------------------------------------------------------------------------
# Context the turn loads for itself
# ---------------------------------------------------------------------------


async def test_a_fresh_session_rehydrates_the_plan_the_user_has(turn):
    """State lives in the checkpointer, keyed on the session; the plan does not."""
    agent, session, _calls = turn(
        [AIMessage(content="You are on a 4-day upper/lower split.")],
        intent="general_qa",
        saved_plan=PLAN,
    )

    await agent.get_response(_user("what is my plan?"), session, user_id="1")
    state = await agent._graph.aget_state(_thread(session))

    assert state.values["plan"] == PLAN
    assert state.values["macros"] == MACROS
    assert state.values["current_version_id"] == "v-0", "the parent of the next save was not set"


async def test_an_anonymous_session_loads_nothing_and_still_answers(turn):
    """There is no user to look anything up for, and the turn still owes an answer."""
    agent, session, _calls = turn(
        [AIMessage(content="Reps in reserve — how many you had left.")], intent="general_qa"
    )

    answer = await agent.get_response(_user("what is RIR?"), session)

    assert answer[0].content.startswith("Reps in reserve")
    state = await agent._graph.aget_state(_thread(session))
    assert state.values["profile"] == {}


async def test_the_answer_returned_is_the_answer_recorded(turn):
    """``messages`` is what the checkpointer replays, and it must carry the reply.

    The old graph needed an ``answer`` field and a node to copy it into the
    transcript, because nine terminal branches each set one. The supervisor
    writes a message, so the two cannot disagree — and this asserts they do not.
    """
    agent, session, _calls = turn([AIMessage(content="Three grams a day.")], intent="general_qa")

    answer = await agent.get_response(_user("how much creatine?"), session, user_id="1")
    history = await agent.get_chat_history(session)

    assert answer[0].content == "Three grams a day."
    assert history[-1].content == "Three grams a day."
    assert history[-1].role == "assistant"


async def test_only_user_messages_are_fed_back_in(turn):
    """Replaying stored assistant turns would duplicate them against the checkpoint."""
    agent, session, _calls = turn([AIMessage(content="Noted.")], intent="general_qa")

    await agent.get_response(
        [Message(role="assistant", content="an old reply"), Message(role="user", content="hello")],
        session,
        user_id="1",
    )
    history = await agent.get_chat_history(session)

    assert [m.content for m in history if m.role == "user"] == ["hello"]


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _thread(session: str) -> dict:
    """The config key the checkpointer stores a session under."""
    return {"configurable": {"thread_id": session}}


async def _run_until_gate(agent, session: str, minted: dict) -> list[Message]:
    """Run the first turn, rewriting the scripted save call with the real handle.

    The draft id is minted while the turn runs, so a script written in advance
    cannot name it. The model's second response is patched between calls, which
    is the same thing a real model does — it reads the handle out of the tool
    result.

    Args:
        agent: The facade under test.
        session: Session id.
        minted: The dict the planning stub records its handle in.

    Returns:
        What the facade returned, which is the confirm question.
    """
    from app.services.llm.registry import LLMRegistry

    model = LLMRegistry.get_llm("any")

    def _rewrite() -> None:
        draft_id = minted.get("draft_id")
        if not draft_id:
            return
        for response in model.responses:
            for tool_request in response.tool_calls or []:
                if tool_request["name"] == "save_plan":
                    tool_request["args"] = {"draft_id": draft_id}

    model.on_call = _rewrite
    return await agent.get_response(_user("build me a plan"), session, user_id="1")


# ---------------------------------------------------------------------------
# Streaming
# ---------------------------------------------------------------------------


def test_only_the_supervisors_own_tokens_reach_the_chat_window():
    """A subagent's reasoning must not stream into the user's conversation.

    The supervisor's tool-calling turns emit no text and fall out on their own.
    A subagent's do not: it runs inside a tool body, under a checkpoint namespace
    nested below ``tools``, and its tokens would otherwise appear as though the
    assistant were thinking out loud about slot ids.
    """
    from app.core.langgraph.graph import _is_supervisor_answer

    assert _is_supervisor_answer({"langgraph_node": "model", "langgraph_checkpoint_ns": "model:1"})
    assert not _is_supervisor_answer(
        {"langgraph_node": "model", "langgraph_checkpoint_ns": "tools:9|planning:2|model:3"}
    )
    assert not _is_supervisor_answer({"langgraph_node": "tools", "langgraph_checkpoint_ns": ""})
    assert not _is_supervisor_answer({})


async def test_an_off_topic_turn_touches_no_store(turn, monkeypatch):
    """The gate ends the turn before the context load, so nothing is queried."""

    def refuse(*_args, **_kwargs):
        raise AssertionError("an off-topic turn read the database")

    agent, session, _calls = turn([AIMessage(content="should not run")], intent="off_topic")
    monkeypatch.setattr(
        "app.core.langgraph.supervisor.middleware.profile_service.get_profile", refuse
    )
    monkeypatch.setattr("app.core.langgraph.supervisor.middleware.latest_version", refuse)

    answer = await agent.get_response(_user("who won the cup?"), session, user_id="1")

    from app.core.langgraph.supervisor import OFF_TOPIC_ANSWER

    assert answer[0].content == OFF_TOPIC_ANSWER
