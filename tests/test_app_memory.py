"""Tests for episodic memory.

Episodic memory is the one subsystem here that is *optional to the answer*.
Everything it does must therefore fail soft: an unreachable Postgres, a slow
summariser — neither may cost the user their reply. The tests below are mostly
about that, plus the one thing that must never fail soft: keeping one user's
history away from another's.

Semantic memory has no tests of its own here any more. It is ``user_profile``,
covered by the profile and pipeline suites, and there is no service in front of
it to fail.
"""

import asyncio

import pytest


@pytest.fixture
def episodic_db(monkeypatch):
    """A throwaway in-memory schema for the episodic tables.

    Built with an explicit table list and its own engine, never
    ``app.models.database.engine``: that one is bound to the developer's
    Postgres at import, and whole-metadata DDL against it once dropped real
    tables (see the note in ``tests/test_auth_flow.py``).

    Foreign keys are enforced. SQLite ignores them unless asked, and the one
    constraint that matters here — ``plan_versions.session_id`` being
    ``ON DELETE SET NULL`` — is invisible without them.
    """
    from sqlalchemy import event
    from sqlalchemy.pool import StaticPool
    from sqlmodel import SQLModel, create_engine

    import app.services.episodes as episodes
    from app.models.plan_version import PlanVersion  # noqa: F401  (registers the table)
    from app.models.session import Session as ChatSession  # noqa: F401
    from app.models.user import User  # noqa: F401  (both tables carry an FK to it)

    engine = create_engine(
        "sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool
    )

    @event.listens_for(engine, "connect")
    def _enforce_foreign_keys(connection, _record):
        connection.execute("PRAGMA foreign_keys=ON")

    tables = [SQLModel.metadata.tables[name] for name in ("user", "session", "plan_versions")]
    SQLModel.metadata.create_all(engine, tables=tables)
    monkeypatch.setattr(episodes, "engine", engine)
    return engine


def _make_session(engine, session_id: str, *, user_id: int = 1, idle_minutes: int = 0, **fields):
    """Insert one chat session, last active ``idle_minutes`` ago.

    Creates the owning user if it is missing: the fixture enforces foreign keys,
    so a session without one cannot be inserted.
    """
    from datetime import UTC, datetime, timedelta

    from sqlmodel import Session as DBSession

    from app.models.session import Session as ChatSession
    from app.models.user import User

    # Naive UTC, matching `episodes._utcnow` and the column type. An aware value
    # here would compare against the cutoff through a timezone conversion and
    # make the staleness tests mean something other than what they read as.
    now = datetime.now(UTC).replace(tzinfo=None)
    with DBSession(engine) as db:
        if db.get(User, user_id) is None:
            db.add(User(id=user_id, email=f"user{user_id}@example.com", hashed_password="x"))
            db.commit()
        db.add(
            ChatSession(
                id=session_id,
                user_id=user_id,
                last_activity_at=now - timedelta(minutes=idle_minutes),
                **fields,
            )
        )
        db.commit()


def _minutes_ago(minutes: int):
    """A naive UTC timestamp, matching the column type and ``episodes._utcnow``."""
    from datetime import UTC, datetime, timedelta

    return datetime.now(UTC).replace(tzinfo=None) - timedelta(minutes=minutes)


async def test_an_anonymous_turn_has_no_episodes_and_sweeps_nothing(episodic_db):
    """The isolation boundary is the same as long-term memory's: no user, no data."""
    from app.services.episodes import recent_episodes, summarize_stale_sessions

    _make_session(episodic_db, "old", idle_minutes=999, summary="they built a plan")

    assert await recent_episodes(None, "current") == ""

    calls = []
    summarize_stale_sessions(None, "current", lambda sid: calls.append(sid))
    assert calls == []


async def test_episodes_are_scoped_to_the_user(episodic_db):
    """One user's history must never appear in another's prompt."""
    from app.services.episodes import recent_episodes

    _make_session(episodic_db, "mine", user_id=1, idle_minutes=60, summary="my conversation")
    _make_session(episodic_db, "theirs", user_id=2, idle_minutes=60, summary="their conversation")

    rendered = await recent_episodes("1", "current")
    assert "my conversation" in rendered
    assert "their conversation" not in rendered


async def test_the_current_session_is_excluded(episodic_db):
    """The checkpointer already replays this session; repeating it wastes context."""
    from app.services.episodes import recent_episodes

    _make_session(episodic_db, "current", idle_minutes=60, summary="this very conversation")

    assert await recent_episodes("1", "current") == ""


async def test_a_query_failure_returns_empty_rather_than_raising(episodic_db, monkeypatch):
    """Episodic memory is optional to the answer, like every other memory read."""
    import app.services.episodes as episodes

    monkeypatch.setattr(episodes, "engine", object())
    assert await episodes.recent_episodes("1", "current") == ""


async def test_a_session_is_claimed_exactly_once(episodic_db):
    """Two workers sweeping at the same moment must not both pay for a summary.

    The claim is the same UPDATE that selects the row, so the loser's row count
    is zero and it fires nothing.
    """
    from app.services.episodes import _claim_stale_sessions

    _make_session(episodic_db, "idle", idle_minutes=999)

    first = _claim_stale_sessions(1, "current")
    second = _claim_stale_sessions(1, "current")

    assert first == ["idle"]
    assert second == [], "a claimed session was handed out twice"


async def test_an_active_session_is_not_summarized(episodic_db):
    """Idleness is the only 'this conversation ended' signal there is."""
    from app.services.episodes import _claim_stale_sessions

    _make_session(episodic_db, "still-going", idle_minutes=1)

    assert _claim_stale_sessions(1, "current") == []


async def test_a_failed_summary_is_never_retried(episodic_db, monkeypatch):
    """The claim is written before the model call, on purpose.

    A session whose summary always fails would otherwise cost an LLM call on
    every turn the user takes from then on. Losing the summary costs recall; the
    turn itself is untouched.
    """
    from sqlmodel import Session as DBSession

    import app.services.episodes as episodes
    from app.models.session import Session as ChatSession

    _make_session(episodic_db, "idle", idle_minutes=999)

    attempts = []

    async def _boom(_messages, **_kwargs):
        attempts.append(1)
        raise RuntimeError("model unavailable")

    monkeypatch.setattr(episodes.llm_service, "call", _boom)

    async def _transcript(_session_id):
        from app.schemas.chat import Message

        return [Message(role="user", content="build me a plan")]

    episodes.summarize_stale_sessions(1, "current", _transcript)
    for _ in range(4):
        await asyncio.sleep(0)

    assert attempts, "the model was never called — the test proved nothing"

    with DBSession(episodic_db) as db:
        row = db.get(ChatSession, "idle")
        assert row.summary == "", "a failed call must not write a summary"
        assert row.summarized_at is not None, "the claim must survive the failure"

    assert episodes._claim_stale_sessions(1, "current") == []


async def test_a_summary_is_written_in_the_background(episodic_db, monkeypatch):
    """The user waits for their answer, not for the assistant's notes."""
    from sqlmodel import Session as DBSession

    import app.services.episodes as episodes
    from app.models.session import Session as ChatSession
    from app.schemas.chat import SessionSummary

    _make_session(episodic_db, "idle", idle_minutes=999)

    async def _summarize(_messages, **_kwargs):
        return SessionSummary(summary="a fat-loss plan was built and saved")

    monkeypatch.setattr(episodes.llm_service, "call", _summarize)

    async def _transcript(_session_id):
        from app.schemas.chat import Message

        return [Message(role="user", content="build me a fat-loss plan")]

    episodes.summarize_stale_sessions(1, "current", _transcript)

    with DBSession(episodic_db) as db:
        assert db.get(ChatSession, "idle").summary == "", "the write blocked the caller"

    for _ in range(4):
        await asyncio.sleep(0)

    with DBSession(episodic_db) as db:
        assert db.get(ChatSession, "idle").summary == "a fat-loss plan was built and saved"


async def test_a_session_summarizes_itself_when_a_turn_ends(episodic_db, monkeypatch):
    """The write the whole layer hangs on.

    No idle window and no claim: the session being chatted in right now is the
    one summarised, so the account of it is already in the database by the time
    the user opens their next conversation. Waiting for it to go quiet instead
    is what made episodic memory one turn late — the summary landed after the
    next session had read.
    """
    from sqlmodel import Session as DBSession

    import app.services.episodes as episodes
    from app.models.session import Session as ChatSession
    from app.schemas.chat import SessionSummary

    _make_session(episodic_db, "current", idle_minutes=0)

    async def _summarize(_messages, **_kwargs):
        return SessionSummary(summary="they dropped to 3 days for work travel")

    monkeypatch.setattr(episodes.llm_service, "call", _summarize)

    async def _transcript(_session_id):
        from app.schemas.chat import Message

        return [Message(role="user", content="I can only train 3 days")]

    episodes.summarize_current_session(1, "current", _transcript)

    with DBSession(episodic_db) as db:
        assert db.get(ChatSession, "current").summary == "", "the write blocked the turn"

    for _ in range(4):
        await asyncio.sleep(0)

    with DBSession(episodic_db) as db:
        assert db.get(ChatSession, "current").summary == "they dropped to 3 days for work travel"


async def test_a_summarized_turn_takes_its_session_out_of_the_sweep(episodic_db, monkeypatch):
    """The two writers must not pay twice for the same conversation.

    ``summarized_at`` is written with the summary, and the turn touched
    ``last_activity_at`` before it, so the sweep's predicate no longer matches
    however long the session then sits idle.
    """
    import app.services.episodes as episodes
    from app.schemas.chat import SessionSummary

    _make_session(episodic_db, "past", idle_minutes=999)

    async def _summarize(_messages, **_kwargs):
        return SessionSummary(summary="a plan was built")

    monkeypatch.setattr(episodes.llm_service, "call", _summarize)

    async def _transcript(_session_id):
        from app.schemas.chat import Message

        return [Message(role="user", content="build me a plan")]

    episodes.summarize_current_session(1, "past", _transcript)
    for _ in range(4):
        await asyncio.sleep(0)

    assert episodes._claim_stale_sessions(1, "current") == [], (
        "a session already summarised by its own turn was swept again"
    )


async def test_a_lost_turn_end_summary_is_collected_by_the_sweep(episodic_db, monkeypatch):
    """The failure the idle sweep still exists for.

    A model call that failed, a stream the client aborted, a worker that died
    holding the task: none of them write ``summarized_at``, so the session is
    still eligible once it goes quiet.
    """
    import app.services.episodes as episodes

    _make_session(episodic_db, "past", idle_minutes=999)

    async def _boom(_messages, **_kwargs):
        raise RuntimeError("model unavailable")

    monkeypatch.setattr(episodes.llm_service, "call", _boom)

    async def _transcript(_session_id):
        from app.schemas.chat import Message

        return [Message(role="user", content="build me a plan")]

    episodes.summarize_current_session(1, "past", _transcript)
    for _ in range(4):
        await asyncio.sleep(0)

    assert episodes._claim_stale_sessions(1, "current") == ["past"]


async def test_an_anonymous_turn_summarizes_nothing(episodic_db):
    """Same boundary as the sweep and as retrieval: no user, no episode.

    An anonymous session has nobody to carry its history forward to, so paying
    for a summary of it buys nothing.
    """
    import app.services.episodes as episodes

    _make_session(episodic_db, "current", idle_minutes=0)

    calls = []
    episodes.summarize_current_session(None, "current", lambda sid: calls.append(sid))
    for _ in range(4):
        await asyncio.sleep(0)

    assert calls == []


async def test_episodes_name_the_plan_each_session_produced(episodic_db):
    """The FK is what replaces a graph store: which conversation made which plan.

    Derived from `plan_versions.session_id` rather than a timestamp window, so a
    user with two open sessions does not get a version attributed to the wrong
    one.
    """
    from sqlmodel import Session as DBSession

    from app.models.plan_version import PlanVersion
    from app.services.episodes import recent_episodes

    _make_session(episodic_db, "past", idle_minutes=60, summary="a plan was built")
    _make_session(episodic_db, "other", idle_minutes=60, summary="something else happened")
    with DBSession(episodic_db) as db:
        db.add(PlanVersion(id="v-1", user_id=1, session_id="past", label="v1"))
        db.add(PlanVersion(id="v-2", user_id=1, session_id="other", label="v9"))
        db.commit()

    rendered = await recent_episodes("1", "current")
    built = next(line for line in rendered.splitlines() if "a plan was built" in line)
    other = next(line for line in rendered.splitlines() if "something else" in line)

    assert "saved v1" in built
    assert "v9" not in built, "a version from another session was attributed here"
    assert "saved v9" in other


async def test_a_session_is_resummarized_only_after_it_is_talked_in_again(episodic_db):
    """A one-shot claim freezes a conversation at whatever turn it was swept on.

    Summarised at turn 2 of 20, the other eighteen never exist as far as the next
    session is concerned, and the half-finished summary is what every later turn
    reads. Eligibility is therefore "never summarised, or talked in since it was".

    Both halves are asserted, because the second is what keeps a session whose
    summary *failed* from costing an LLM call on every turn forever: no new
    activity, no new attempt.
    """
    import app.services.episodes as episodes

    # Summarised three hours ago, talked in two hours ago: the summary is stale.
    _make_session(episodic_db, "moved-on", idle_minutes=120, summarized_at=_minutes_ago(180))
    # Talked in three hours ago, summarised two hours ago: nothing new to say.
    _make_session(episodic_db, "settled", idle_minutes=180, summarized_at=_minutes_ago(120))

    assert episodes._claim_stale_sessions(1, "current") == ["moved-on"]


async def test_a_session_that_produced_a_plan_outranks_one_that_did_not(episodic_db, monkeypatch):
    """Preference, not filter: with room for two, the plans win.

    Measured on the development database, 3 of 5 summarised sessions produced
    nothing and were pushing the ones that did out of the window. A conversation
    with an outcome says more about what the user is doing than one that wandered.
    """
    from sqlmodel import Session as DBSession

    from app.models.plan_version import PlanVersion
    from app.services.episodes import recent_episodes

    monkeypatch.setattr("app.services.episodes.settings.EPISODIC_RECENT_LIMIT", 2)

    _make_session(episodic_db, "chatter-new", idle_minutes=10, summary="asked about creatine")
    _make_session(episodic_db, "chatter-old", idle_minutes=20, summary="asked about sleep")
    _make_session(episodic_db, "built", idle_minutes=9999, summary="a plan was built")
    with DBSession(episodic_db) as db:
        db.add(PlanVersion(id="v-1", user_id=1, session_id="built", label="v1"))
        db.commit()

    rendered = await recent_episodes("1", "current")

    assert "a plan was built" in rendered, "the only session with an outcome was crowded out"
    assert "asked about sleep" not in rendered, "the older chatter should have lost the slot"
    # Selected by preference, rendered by date: the oldest line must still read
    # last, or the model will describe it as the recent one.
    assert rendered.splitlines()[-1].endswith("(saved v1)")


async def test_identical_summaries_are_collapsed_to_one_line(episodic_db):
    """Three real sessions four minutes apart, all saying the same thing.

    Not a rendering fault, which is why the fix is here and not in the query.
    Five lines spent saying one thing crowd out four other conversations. The
    surviving line keeps the plan label of the copies it absorbed — the version
    link is the one thing a duplicate can hold that its twin does not.
    """
    from sqlmodel import Session as DBSession

    from app.models.plan_version import PlanVersion
    from app.services.episodes import recent_episodes

    for index, idle in enumerate((10, 14, 18)):
        _make_session(
            episodic_db, f"protein-{index}", idle_minutes=idle, summary="Discussed protein intake."
        )
    with DBSession(episodic_db) as db:
        db.add(PlanVersion(id="v-1", user_id=1, session_id="protein-2", label="v3"))
        db.commit()

    rendered = await recent_episodes("1", "current")

    assert rendered.count("Discussed protein intake") == 1
    assert "saved v3" in rendered, "the absorbed session's plan link was dropped"


async def test_deleting_a_conversation_keeps_the_plan_it_produced(episodic_db):
    """`plan_versions` outranks `session`, so the FK is ON DELETE SET NULL.

    The default RESTRICT would make `DELETE /auth/sessions/{id}` start failing
    for anyone who ever built a plan, and CASCADE would delete the plan they are
    training on because they tidied up their chat list. Only the link goes.
    """
    from sqlmodel import Session as DBSession

    from app.models.plan_version import PlanVersion
    from app.models.session import Session as ChatSession

    _make_session(episodic_db, "past", idle_minutes=60, summary="a plan was built")
    with DBSession(episodic_db) as db:
        db.add(PlanVersion(id="v-1", user_id=1, session_id="past", label="v1"))
        db.commit()

    with DBSession(episodic_db) as db:
        db.delete(db.get(ChatSession, "past"))
        db.commit()

    with DBSession(episodic_db) as db:
        version = db.get(PlanVersion, "v-1")
        assert version is not None, "deleting a chat destroyed the user's plan"
        assert version.session_id is None


async def test_the_summary_prompt_forbids_numbers():
    """The mitigation for the one real risk this layer adds.

    This text reaches the system prompt on every later turn, and the workflow
    doc records what happens when a free-text memory carries a number the plan
    disagrees with: the model states the memory's number.
    """
    from app.core.prompts import SESSION_SUMMARY_PROMPT

    assert "Never state a number" in SESSION_SUMMARY_PROMPT


# ---------------------------------------------------------------------------
# One read per turn
# ---------------------------------------------------------------------------


def test_no_agent_loads_the_profile_for_itself():
    """Every memory layer is read once, at the root, and passed down.

    The rule outlived the backend it was written for. mem0 is gone and semantic
    memory is now ``user_profile``, so the way to break this is an agent calling
    ``get_profile`` rather than ``memory_service.search`` — and the cost is the
    same: one query per agent instead of one per turn, and two agents reasoning
    over a profile the other has not seen. `load_context` reads it; agents get
    it rendered.
    """
    from pathlib import Path

    agents_dir = Path(__file__).resolve().parent.parent / "app" / "core" / "langgraph" / "agents"
    offenders = [
        path.relative_to(agents_dir).as_posix()
        for path in agents_dir.rglob("*.py")
        if "get_profile" in path.read_text(encoding="utf-8")
    ]
    assert offenders == [], f"agents loading the profile directly: {offenders}"


def test_no_agent_retrieves_episodes_for_itself():
    """Episodic memory obeys the same rule: retrieved once, at the root.

    Agents receive `episodic_context` in their mapped-in state. One reaching for
    `recent_episodes` would issue a second query per turn and could see a
    different history than the node that already reasoned over one.
    """
    from pathlib import Path

    agents_dir = Path(__file__).resolve().parent.parent / "app" / "core" / "langgraph" / "agents"
    offenders = [
        path.relative_to(agents_dir).as_posix()
        for path in agents_dir.rglob("*.py")
        if "recent_episodes" in path.read_text(encoding="utf-8")
    ]
    assert offenders == [], f"agents retrieving episodes directly: {offenders}"


def test_the_qa_agent_reads_memory_from_state():
    """The one agent that personalises must receive memory, not fetch it."""
    from app.core.langgraph.agents.qa import QAState

    assert "semantic_context" in QAState.__annotations__
    assert "episodic_context" in QAState.__annotations__


def test_the_answer_is_told_where_a_number_may_come_from():
    """A recorded failure, and now a weaker guard than it used to be.

    ``_compose_answer`` once announced a 5-day plan as 4-day, sourcing the number
    from long-term memory rather than from the rendered plan it was handed. The
    fix was structural: episodic context was withheld from that node entirely, so
    there was no second free-text account of the plan for it to misread.

    That structure is gone with the node. The supervisor both reads the history
    and writes the answer, so the two cannot be separated by withholding — which
    makes this a prompt rule, and a prompt rule is weaker than an absent field.
    What is asserted here is that the rule is stated and that the authoritative
    section it points at is rendered above it, so a prompt edit that drops either
    fails rather than passing quietly.
    """
    from app.core.prompts import load_supervisor_prompt

    prompt = load_supervisor_prompt(
        semantic_context="- Body weight (kg): 75",
        plan_context="Plan: 5 days",
        episodic_context="In March they trained 4 days a week.",
    )

    plan_section = prompt.index("# This user's plan")
    history_section = prompt.index("# What happened in earlier conversations")

    assert plan_section < history_section, "history is rendered above the plan it must not override"
    assert "never to state what their plan holds now" in prompt
    assert "Never retype numbers" in prompt


# ---------------------------------------------------------------------------
# Reading model output
# ---------------------------------------------------------------------------


def test_reasoning_model_content_blocks_are_read_as_text():
    """A reasoning model returns content *blocks*, not a string.

    This is the failure a real API call exposed and 196 stubbed tests did not:
    every stub returned ``AIMessage(content="...")`` with a plain string, while
    the live model returned ``[{'type': 'reasoning'}, {'type': 'text'}]``. The
    old `content if isinstance(content, str) else ""` yielded an empty answer —
    nothing raised, the turn "succeeded", and the user got nothing.
    """
    from langchain_core.messages import AIMessage

    from app.core.langgraph.utils import message_text

    blocks = AIMessage(
        content=[
            {"type": "reasoning", "reasoning": "thinking about it"},
            {"type": "text", "text": "Here is your plan."},
        ]
    )
    assert message_text(blocks) == "Here is your plan."
    assert message_text(AIMessage(content="plain string")) == "plain string"
    assert message_text(AIMessage(content=[])) == ""


def test_no_node_reads_content_directly():
    """`message_text` is the only correct way to read a model response.

    A direct `.content` read reintroduces the empty-answer bug for reasoning
    models, and it does so silently.
    """
    from pathlib import Path

    root = Path(__file__).resolve().parent.parent / "app"
    offenders = [
        f"{path.relative_to(root)}:{n}"
        for path in root.rglob("*.py")
        if path.name != "utils.py"
        for n, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1)
        if "isinstance(" in line and ".content, str)" in line
    ]
    assert offenders == [], f"reads .content directly instead of message_text: {offenders}"
