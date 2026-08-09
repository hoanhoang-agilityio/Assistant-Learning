"""Episodic memory: what happened in this user's earlier conversations.

The LangGraph checkpointer is keyed by ``thread_id = session_id``, so a new chat
starts blind — the user's plan history is in Postgres but the account of how
they got there is not. Semantic memory (``user_profile``) survives the boundary,
but it stores *facts*, typed and undated. "Trains four days a week" is a fact;
"three weeks ago they asked to drop to 3 days because of work travel, and the
plan was rebuilt" is an episode, and it is what a question like "what did I
change last time?" is actually asking for.

This module writes one summary per finished session and reads back the most
recent few. Four rules, each with a failure it prevents:

**Summarising is claimed, and the claim expires when the conversation moves on.**
``session.summarized_at`` is set by the same ``UPDATE`` that selects the session,
so several uvicorn workers sweeping at the same moment cannot each pay for the
same summary. A session is eligible again once ``last_activity_at`` passes
``summarized_at`` — otherwise a conversation summarised at turn 2 of 20 would
record those two turns and freeze, and the other eighteen would never exist as
far as the next session is concerned.

That still leaves a failed summary un-retried, which is the intended trade: the
claim is written *before* the model call, so a session that always fails does not
cost an LLM call on every later turn. It is retried only when there is something
new to summarise.

**Nothing here blocks or fails a turn.** The sweep is one ``UPDATE`` and returns;
the model call runs in the background; every read catches and returns ``""``.

**Retrieval is chronological, not semantic.** "Last time", "three weeks ago",
"the one before that" are questions about *when*, and a nearest-neighbour search
answers a different question — the same boundary ``app/models/knowledge.py``
draws between pgvector and an exact query. Also keeps a turn reproducible.

Within that, sessions that produced a saved plan are preferred, because a
conversation with an outcome says more than one that wandered. Preference, not
filter: the ordering decides which few are carried, and they are still rendered
newest first.

**One retrieval per turn, at the root.** Same rule as semantic memory: agents
read ``episodic_context`` out of state and never query for themselves.
"""

import asyncio
from collections.abc import Awaitable, Callable
from datetime import UTC, datetime, timedelta
from typing import Any, Protocol

from langchain_core.messages import HumanMessage, SystemMessage
from sqlalchemy import or_
from sqlmodel import Session as DBSession
from sqlmodel import col, select, update

from app.core.configs.config import settings
from app.core.logging import logger
from app.core.prompts import SESSION_SUMMARY_PROMPT
from app.models.database import engine
from app.models.plan_version import PlanVersion
from app.models.session import Session as ChatSession
from app.schemas.chat import SessionSummary
from app.services.llm import llm_service

# What the caller substitutes when nothing is retrieved, so the prompt reads the
# same whether there were no earlier sessions, the feature is off, or the query
# failed.
NO_EPISODES = ""

# Transcript characters sent to the summariser. A long conversation is truncated
# from the *start*, because the end of a session is where the outcome is.
_TRANSCRIPT_MAX = 6000

# Sessions summarised per sweep. A user returning after a long gap may have
# several idle sessions; doing them all in one turn would fire a burst of LLM
# calls, and the oldest are the least useful anyway.
_SWEEP_LIMIT = 3

# Strong references to in-flight background summaries. `create_task` alone
# leaves only a weak reference and the write can vanish mid-flight.
_BACKGROUND_TASKS: set[asyncio.Task] = set()


def _utcnow() -> datetime:
    """Return the current UTC time as a naive datetime.

    ``session.last_activity_at`` and ``summarized_at`` are ``TIMESTAMP WITHOUT
    TIME ZONE``, and this module compares against them (``last_activity_at <
    cutoff``) rather than only writing them. An aware datetime would be handed
    to Postgres as ``timestamptz`` and compared through the session's TimeZone
    setting, so the sweep's cutoff would silently shift with the server's
    configuration. Naive on both sides makes the comparison mean one thing.

    Returns:
        Now, in UTC, without a tzinfo.
    """
    return datetime.now(UTC).replace(tzinfo=None)


class _Transcribable(Protocol):
    """The shape of a stored message, as ``to_chat_messages`` returns it."""

    role: str
    content: str


TranscriptLoader = Callable[[str], Awaitable[list[Any]]]
"""Reads a session's messages from the checkpointer.

Passed in rather than imported. ``LangGraphAgent`` already imports this module's
sibling services, so reaching back into the graph from here would close an
import cycle — and it lets the tests summarise a transcript without a
checkpointer.
"""


def _render_transcript(messages: list[_Transcribable]) -> str:
    """Format a stored conversation for the summariser.

    Args:
        messages: The session's messages, oldest first.

    Returns:
        One ``role: content`` line per message, truncated to the most recent
        ``_TRANSCRIPT_MAX`` characters, or ``""`` when there is nothing to say.
    """
    lines = [
        f"{message.role}: {message.content}"
        for message in messages
        if getattr(message, "content", "")
    ]
    if not lines:
        return ""
    return "\n".join(lines)[-_TRANSCRIPT_MAX:]


def touch_session(session_id: str) -> None:
    """Record that a turn just ran in this session. Never raises.

    Idleness is the only available signal that a conversation has ended, so this
    is what makes the sweep work at all. It is a single ``UPDATE`` of one
    indexed column.

    Args:
        session_id: The session being chatted in.
    """
    try:
        with DBSession(engine) as db:
            db.exec(
                update(ChatSession)
                .where(col(ChatSession.id) == session_id)
                .values(last_activity_at=_utcnow())
            )
            db.commit()
    except Exception:
        # Costs the next sweep its accuracy, not this turn its answer.
        logger.warning("episode_touch_failed", session_id=session_id)


def _claim_stale_sessions(user_id: int, exclude_session_id: str) -> list[str]:
    """Claim every idle session of this user's whose summary is missing or stale.

    Select and claim are one statement on purpose. A ``SELECT`` followed by an
    ``UPDATE`` reopens exactly the race this closes: two workers reading the
    same idle session and both paying for its summary.

    Args:
        user_id: Owner of the sessions.
        exclude_session_id: The session the user is chatting in right now, which
            is by definition not finished.

    Returns:
        Ids this caller won and must now summarise. Empty is the common case.
    """
    cutoff = _utcnow() - timedelta(minutes=settings.EPISODIC_IDLE_MINUTES)
    # Never summarised, or talked in since it was. The second half is what makes
    # the claim refreshable rather than one-shot — see the module docstring.
    #
    # It is also what closes the race, and it stays correct for that: the claim
    # writes `summarized_at = now`, and a session only reaches here after sitting
    # idle past the cutoff, so `last_activity_at` is already in the past and a
    # second worker's UPDATE matches no rows.
    needs_summary = or_(
        col(ChatSession.summarized_at).is_(None),
        col(ChatSession.summarized_at) < col(ChatSession.last_activity_at),
    )

    with DBSession(engine) as db:
        candidates = db.exec(
            select(ChatSession.id)
            .where(
                col(ChatSession.user_id) == user_id,
                col(ChatSession.id) != exclude_session_id,
                needs_summary,
                col(ChatSession.last_activity_at).is_not(None),
                col(ChatSession.last_activity_at) < cutoff,
            )
            .order_by(col(ChatSession.last_activity_at).desc())
            .limit(_SWEEP_LIMIT)
        ).all()

        claimed = []
        for session_id in candidates:
            result = db.exec(
                update(ChatSession)
                .where(col(ChatSession.id) == session_id, needs_summary)
                .values(summarized_at=_utcnow())
            )
            if (result.rowcount or 0) == 1:
                claimed.append(session_id)
        db.commit()

    return claimed


def _store_summary(session_id: str, summary: str) -> None:
    """Write a generated summary onto its session row.

    Args:
        session_id: The claimed session.
        summary: The generated text.
    """
    with DBSession(engine) as db:
        db.exec(
            update(ChatSession).where(col(ChatSession.id) == session_id).values(summary=summary)
        )
        db.commit()


async def _persist_summary(session_id: str, load_transcript: TranscriptLoader) -> None:
    """Summarise one claimed session and store it. Never raises.

    Args:
        session_id: The session this caller claimed.
        load_transcript: Reads the session's messages from the checkpointer.
    """
    try:
        transcript = _render_transcript(await load_transcript(session_id))
        if not transcript:
            # Claimed and empty: a session the user opened and abandoned. The
            # claim stays, so it is never looked at again.
            logger.info("episode_skipped_empty", session_id=session_id)
            return

        result = await llm_service.call(
            [
                SystemMessage(content=SESSION_SUMMARY_PROMPT),
                HumanMessage(content=transcript),
            ],
            model_name=settings.EPISODIC_SUMMARY_MODEL,
            response_format=SessionSummary,
            reasoning={"effort": "low"},
            max_tokens=256,
            temperature=0.3,
        )
        _store_summary(session_id, result.summary)
        logger.info("episode_summarized", session_id=session_id)
    except Exception:
        # The claim is already written, so this is not retried. A missing
        # summary costs recall on a later turn and nothing on this one.
        logger.exception("episode_summary_failed", session_id=session_id)


def maybe_summarize_stale_sessions(
    user_id: int | str | None, current_session_id: str, load_transcript: TranscriptLoader
) -> None:
    """Start summarising any of this user's conversations that have gone idle.

    Synchronous by design, like ``maybe_name_session``: it opens one short
    database session and returns, so a caller cannot accidentally await the
    summarising. Safe to call from any chat endpoint on every turn.

    Args:
        user_id: Owner of the sessions. ``None`` for an anonymous turn, which
            has no history to build.
        current_session_id: The session being chatted in, never swept.
        load_transcript: Reads a session's messages from the checkpointer.
    """
    if not settings.EPISODIC_MEMORY_ENABLED or not user_id:
        return

    touch_session(current_session_id)

    try:
        claimed = _claim_stale_sessions(int(user_id), current_session_id)
    except Exception:
        logger.exception("episode_sweep_failed", user_id=user_id)
        return

    for session_id in claimed:
        task = asyncio.create_task(_persist_summary(session_id, load_transcript))
        _BACKGROUND_TASKS.add(task)
        task.add_done_callback(_BACKGROUND_TASKS.discard)


def _newest_first(sessions: list[ChatSession]) -> list[ChatSession]:
    """Sort retrieved sessions back into chronological order.

    They are *selected* by preference — a session that produced a plan outranks
    one that did not, however old it is — and that ordering has no business
    reaching the prompt. What the model reads is a history, and a history that
    is not in order invites it to describe an old session as the recent one.

    Args:
        sessions: The selected sessions, in whatever order the query returned.

    Returns:
        The same sessions, newest first.
    """
    return sorted(
        sessions, key=lambda session: session.last_activity_at or session.created_at, reverse=True
    )


def _dedupe(rows: list[tuple[ChatSession, list[str]]]) -> list[tuple[ChatSession, list[str]]]:
    """Collapse sessions whose summaries say the same thing.

    Three near-identical lines about protein were three real sessions four
    minutes apart, not a rendering fault — so the fix belongs here rather than in
    the query. Five lines of prompt spent saying one thing crowds out the four
    other conversations that would have fit.

    Matching is on normalised text, so it collapses the identical and leaves
    genuinely different wording alone. Summaries that differ by a word survive as
    two lines; tightening those is the summariser prompt's job, not this
    function's guesswork.

    Args:
        rows: Sessions newest first, each with the plan-version labels it
            produced.

    Returns:
        The same rows with duplicates removed, order preserved.
    """
    seen: dict[str, int] = {}
    kept: list[tuple[ChatSession, list[str]]] = []

    for session, labels in rows:
        key = " ".join(session.summary.lower().split())
        index = seen.get(key)

        if index is None:
            seen[key] = len(kept)
            kept.append((session, list(labels)))
            continue

        # The newest copy is already kept, because `rows` arrives newest first.
        # Only the labels of the older ones are carried over: the version link is
        # the one thing a duplicate can hold that its twin does not, and dropping
        # it would lose which plan came out of that conversation.
        older_session, merged = kept[index]
        merged.extend(label for label in labels if label not in merged)
        kept[index] = (older_session, merged)

    return kept


def _render_episodes(rows: list[tuple[ChatSession, list[str]]]) -> str:
    """Format retrieved sessions for the prompt.

    Args:
        rows: Sessions newest first, each with the labels of the plan versions
            it produced.

    Returns:
        One dated line per session.
    """
    lines = []
    for session, labels in rows:
        when = session.last_activity_at or session.created_at
        date = when.strftime("%Y-%m-%d") if when else "unknown date"
        produced = f" (saved {', '.join(labels)})" if labels else ""
        lines.append(f"- {date}: {session.summary}{produced}")
    return "\n".join(lines)


async def recent_episodes(user_id: str | None, exclude_session_id: str) -> str:
    """Retrieve what happened in this user's recent finished sessions.

    Args:
        user_id: Owner of the sessions. ``None`` for an anonymous turn.
        exclude_session_id: The current session, whose own history the
            checkpointer already replays into the conversation.

    Returns:
        Dated summaries newest first, or ``""`` when there are none, the user is
        anonymous, the feature is off, or anything at all went wrong.
    """
    if not settings.EPISODIC_MEMORY_ENABLED or not user_id:
        return NO_EPISODES

    try:
        with DBSession(engine) as db:
            # A preference, not a filter. Measured on the development database:
            # 3 of 5 summarised sessions produced no plan at all, and they were
            # pushing the ones that did out of the window entirely.
            produced_a_plan = (
                select(PlanVersion.id)
                .where(col(PlanVersion.session_id) == col(ChatSession.id))
                .exists()
            )

            sessions = db.exec(
                select(ChatSession)
                .where(
                    col(ChatSession.user_id) == int(user_id),
                    col(ChatSession.id) != exclude_session_id,
                    col(ChatSession.summary) != "",
                )
                .order_by(produced_a_plan.desc(), col(ChatSession.last_activity_at).desc())
                .limit(settings.EPISODIC_RECENT_LIMIT)
            ).all()

            if not sessions:
                return NO_EPISODES

            # The edge that replaces a graph store: which plan came out of which
            # conversation, by foreign key rather than by timestamp overlap.
            versions = db.exec(
                select(PlanVersion).where(col(PlanVersion.session_id).in_([s.id for s in sessions]))
            ).all()
    except Exception as e:
        logger.exception("episode_search_failed", user_id=user_id, error=str(e))
        return NO_EPISODES

    labels: dict[str, list[str]] = {}
    for version in versions:
        if version.session_id:
            labels.setdefault(version.session_id, []).append(version.label)

    rows = _dedupe([(s, labels.get(s.id, [])) for s in _newest_first(sessions)])
    logger.info(
        "episodes_retrieved",
        user_id=user_id,
        sessions=len(rows),
        collapsed=len(sessions) - len(rows),
    )
    return _render_episodes(rows)


__all__ = [
    "NO_EPISODES",
    "maybe_summarize_stale_sessions",
    "recent_episodes",
    "touch_session",
]
