"""The public facade the API depends on, and the resources it owns.

What is behind it changed completely; what it looks like did not. The API still
calls four methods, still does not know subgraphs exist, and still does not
assemble context — the supervisor loads its own, so a caller that is not this
facade is not a degraded caller.

What is left here after the supervisor conversion is exactly the work that is
not the agent's: opening the checkpointer pool, building the runnable config
with the Langfuse handler attached once, and translating between a chat turn and
the agent's notion of a run. That last one is the only subtle part. A thread
parked at an ``interrupt()`` is mid-run, not finished; feeding it a fresh
``{"messages": ...}`` would start a second run over the same state, and the
user's "yes" would be classified as a new request instead of reaching the
confirm gate.
"""

from collections.abc import AsyncGenerator
from typing import Any

from langchain_core.callbacks import BaseCallbackHandler
from langchain_core.messages import AIMessage, BaseMessage, HumanMessage
from langchain_core.runnables import RunnableConfig
from langgraph.checkpoint.postgres.aio import AsyncPostgresSaver
from langgraph.graph.state import CompiledStateGraph
from langgraph.types import Command
from psycopg.rows import dict_row
from psycopg_pool import AsyncConnectionPool

from app.core.configs.config import Environment, settings
from app.core.langgraph.agents import build_all
from app.core.langgraph.supervisor import build_supervisor_with, interrupt_question
from app.core.langgraph.utils import message_text, to_chat_messages
from app.core.logging import logger
from app.core.observability import get_langfuse_callbacks
from app.schemas.chat import Message
from app.services.llm.service import llm_service

GRAPH_NAME = "supervisor"

# Words that count as approval at the confirm gate, across the languages this
# assistant answers in. Anything not listed is treated as "no" — a confirm gate
# that guesses in favour of proceeding is not a gate.
_AFFIRMATIVE = frozenset(
    {
        "yes",
        "y",
        "yeah",
        "yep",
        "ok",
        "okay",
        "sure",
        "confirm",
        "confirmed",
        "apply",
        "save",
        "keep",
        "do it",
        "go ahead",
        "proceed",
        "accept",
        "approve",
        "true",
    }
)

# What the user is told when they decline. Written here rather than left to the
# model: the one thing a decline must communicate is that nothing changed, and a
# model composing that sentence from a rejected tool call has been known to
# apologise for a plan it did not delete.
DECLINED_MESSAGE = (
    "Left your plan as it was. Nothing has changed. Tell me if you want to try a "
    "different adjustment."
)


class LangGraphAgent:
    """Owns the compiled supervisor, its subagents and the checkpointer pool."""

    def __init__(self) -> None:
        """Prepare lazily-created resources."""
        self.llm_service = llm_service
        self._connection_pool: AsyncConnectionPool | None = None
        self._graph: CompiledStateGraph | None = None

    # ------------------------------------------------------------------
    # Resources
    # ------------------------------------------------------------------

    async def _get_connection_pool(self) -> AsyncConnectionPool | None:
        """Open (once) the psycopg pool the checkpointer runs on.

        Deliberately separate from the SQLAlchemy engine in
        ``app/services/database.py``: the checkpointer needs ``autocommit`` and
        raw dict rows, the ORM needs neither, and sharing one pool breaks both.

        Returns:
            The open pool, or ``None`` in production when Postgres is
            unreachable — the app degrades to an unpersisted conversation rather
            than refusing to serve.

        Raises:
            Exception: Propagated outside production, where a missing
                checkpointer should fail loudly during development.
        """
        if self._connection_pool is not None:
            return self._connection_pool

        try:
            pool = AsyncConnectionPool(
                settings.checkpointer_database_uri,
                open=False,
                max_size=settings.POSTGRES_POOL_SIZE,
                kwargs={
                    "autocommit": True,
                    "prepare_threshold": None,
                    "row_factory": dict_row,
                },
            )
            await pool.open()
            self._connection_pool = pool
            return pool
        except Exception:
            if settings.ENVIRONMENT == Environment.PRODUCTION:
                return None
            raise

    async def create_graph(self) -> CompiledStateGraph | None:
        """Build and cache the compiled supervisor.

        Runs once per process. The subagents are built here too, not per
        request: under a supervisor the same agent may be invoked several times
        in one turn, and compiling a graph on each is a real cost.

        Returns:
            The compiled supervisor, or ``None`` when the checkpointer pool
            could not be opened in production.
        """
        if self._graph is not None:
            return self._graph

        try:
            build_all()

            connection_pool = await self._get_connection_pool()
            if connection_pool is not None:
                checkpointer = AsyncPostgresSaver(connection_pool)
                await checkpointer.setup()
            elif settings.ENVIRONMENT == Environment.PRODUCTION:
                checkpointer = None
            else:
                raise RuntimeError("checkpointer pool unavailable outside production")

            self._graph = build_supervisor_with(checkpointer)
            return self._graph
        except Exception as e:
            logger.exception("graph_creation_failed", error=str(e))
            if settings.ENVIRONMENT == Environment.PRODUCTION:
                return None
            raise

    async def _get_graph(self) -> CompiledStateGraph:
        """Return the compiled supervisor, building it on first use.

        Returns:
            The compiled supervisor.

        Raises:
            RuntimeError: When the graph could not be created.
        """
        graph = await self.create_graph()
        if graph is None:
            raise RuntimeError("graph is unavailable — check the database connection")
        return graph

    # ------------------------------------------------------------------
    # Public facade
    # ------------------------------------------------------------------

    async def get_response(
        self,
        messages: list[Message],
        session_id: str,
        user_id: str | None = None,
        username: str | None = None,
    ) -> list[Message]:
        """Process one turn and return the messages produced.

        Args:
            messages: Messages submitted this turn.
            session_id: Session id, used as the checkpointer ``thread_id``.
            user_id: Owner of the session, for trace metadata.
            username: Display name, for trace metadata.

        Returns:
            The assistant messages produced this turn. When the run stopped at a
            confirm gate, the single message is the question to answer.

        Raises:
            Exception: Propagated to the route, which maps it to a 500.
        """
        graph = await self._get_graph()
        config = self._build_config(session_id, user_id, username)

        try:
            await graph.ainvoke(await self._graph_input(graph, config, messages), config)
        except Exception as e:
            logger.exception("graph_invoke_failed", session_id=session_id, error=str(e))
            raise

        interrupt_message = await self._pending_interrupt(graph, config)
        if interrupt_message is not None:
            return [interrupt_message]

        answer = await self._last_answer(graph, config)
        return [Message(role="assistant", content=answer)] if answer else []

    async def get_stream_response(
        self,
        messages: list[Message],
        session_id: str,
        user_id: str | None = None,
        username: str | None = None,
    ) -> AsyncGenerator[str, None]:
        """Stream one turn as text chunks.

        Args:
            messages: Messages submitted this turn.
            session_id: Session id, used as the checkpointer ``thread_id``.
            user_id: Owner of the session, for trace metadata.
            username: Display name, for trace metadata.

        Yields:
            Text chunks as they are produced, then the confirm question if the
            run stopped at one.

        Raises:
            Exception: Propagated to the route, which closes the stream with a
                final frame.
        """
        graph = await self._get_graph()
        config = self._build_config(session_id, user_id, username)

        try:
            async for token, metadata in graph.astream(
                await self._graph_input(graph, config, messages),
                config,
                stream_mode="messages",
            ):
                if not _is_supervisor_answer(metadata):
                    continue
                chunk = message_text(token)
                if chunk:
                    yield chunk
        except Exception as e:
            logger.exception("graph_stream_failed", session_id=session_id, error=str(e))
            raise

        interrupt_message = await self._pending_interrupt(graph, config)
        if interrupt_message is not None:
            yield interrupt_message.content

    async def get_chat_history(self, session_id: str) -> list[Message]:
        """Return the conversation recorded for a session.

        Args:
            session_id: Session id used as the checkpointer ``thread_id``.

        Returns:
            The stored messages, oldest first. Empty when nothing is stored.
        """
        graph = await self._get_graph()
        state = await graph.aget_state({"configurable": {"thread_id": session_id}})
        return to_chat_messages(state.values.get("messages", []))

    async def clear_chat_history(self, session_id: str) -> None:
        """Delete every checkpoint row for a session.

        Args:
            session_id: Session id used as the checkpointer ``thread_id``.

        Raises:
            RuntimeError: When no checkpointer pool is available, so the caller
                never reports a deletion that did not happen.
        """
        await self._get_graph()
        pool = await self._get_connection_pool()
        if pool is None:
            raise RuntimeError("cannot clear history — checkpointer is unavailable")

        async with pool.connection() as conn, conn.pipeline():
            for table in settings.CHECKPOINT_TABLES:
                await conn.execute(f"DELETE FROM {table} WHERE thread_id = %s", (session_id,))

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _build_config(
        self, session_id: str, user_id: str | None, username: str | None
    ) -> RunnableConfig:
        """Assemble the runnable config for one turn.

        The Langfuse handler is attached here and only here; subagent
        invocations inherit it, and a second handler would duplicate every span.

        Args:
            session_id: Session id, used as the checkpointer ``thread_id``.
            user_id: Owner of the session.
            username: Display name.

        Returns:
            The config to pass to every invoke and stream.
        """
        callbacks: list[BaseCallbackHandler] = get_langfuse_callbacks()
        return {
            "configurable": {"thread_id": session_id},
            "callbacks": callbacks,
            "metadata": {
                "user_id": user_id,
                "username": username,
                "session_id": session_id,
                "environment": settings.ENVIRONMENT.value,
                "debug": settings.DEBUG,
            },
        }

    async def _graph_input(
        self, graph: CompiledStateGraph, config: RunnableConfig, messages: list[Message]
    ) -> Any:
        """Decide whether this turn starts a run or resumes a paused one.

        A thread parked at a confirm gate is mid-run. Feeding it a fresh message
        list would start a second run over the same state: the user's "yes" would
        be read as a new request, the gate would never receive it, and the plan
        they were shown would be rebuilt from scratch — possibly differently.

        Resuming means answering the gate, so the reply is translated into the
        decision shape the middleware expects. One decision per pending action,
        because the middleware matches them positionally.

        Args:
            graph: The compiled supervisor.
            config: The config for this thread.
            messages: Messages submitted this turn.

        Returns:
            ``Command(resume=...)`` when the thread is parked, otherwise the
            normal message input.
        """
        state = await graph.aget_state(config)
        pending = _pending_interrupt_value(state)

        if pending is None:
            return {"messages": _to_langchain(messages)}

        reply = next(
            (message.content for message in reversed(messages) if message.role == "user"), ""
        )
        approved = _is_affirmative(reply)
        logger.info("confirm_gate_answered", approved=approved)

        decision: dict[str, Any] = (
            {"type": "approve"}
            if approved
            # `message` is what the model is told, so it does not treat a decline
            # as a failure to retry. The user sees the sentence the facade
            # returns, not this one.
            else {"type": "reject", "message": DECLINED_MESSAGE}
        )
        return Command(resume={"decisions": [decision] * _pending_action_count(pending)})

    async def _pending_interrupt(
        self, graph: CompiledStateGraph, config: RunnableConfig
    ) -> Message | None:
        """Surface a confirm gate the run stopped at, if any.

        Checked after every invoke and stream. Without this the run looks
        complete while the graph is actually parked, and the user is never asked
        the question.

        Args:
            graph: The compiled supervisor.
            config: The config used for the run.

        Returns:
            The question as an assistant message, or ``None`` when the run
            finished normally.
        """
        state = await graph.aget_state(config)
        value = _pending_interrupt_value(state)
        if value is None:
            return None

        return Message(role="assistant", content=interrupt_question(value))

    async def _last_answer(self, graph: CompiledStateGraph, config: RunnableConfig) -> str:
        """Read the answer this turn produced out of the transcript.

        There is no ``answer`` field any more, and there does not need to be: the
        supervisor writes its reply as a message, which is also what the
        checkpointer replays. The old root graph needed both because nine
        terminal branches each set ``answer`` and one node copied it into
        ``messages``.

        Args:
            graph: The compiled supervisor.
            config: The config used for the run.

        Returns:
            The last assistant message's text, or an empty string.
        """
        state = await graph.aget_state(config)
        for message in reversed(state.values.get("messages", [])):
            if isinstance(message, AIMessage):
                return message_text(message)
        return ""


def _pending_interrupt_value(state: Any) -> object | None:
    """Return the payload of an interrupt the run is parked at.

    Args:
        state: A ``StateSnapshot`` from ``aget_state``.

    Returns:
        The interrupt payload, or ``None`` when the run is not parked.
    """
    if not state.next or not state.tasks:
        return None

    for task in state.tasks:
        if task.interrupts:
            return task.interrupts[0].value
    return None


def _pending_action_count(value: object) -> int:
    """Count the actions one interrupt is asking about.

    The middleware matches decisions to requests positionally, so a reply that
    carries the wrong number of decisions is rejected rather than misapplied.

    Args:
        value: The interrupt payload.

    Returns:
        How many decisions the resume must carry. At least one.
    """
    if isinstance(value, dict):
        requests = value.get("action_requests")
        if isinstance(requests, list) and requests:
            return len(requests)
    return 1


def _is_supervisor_answer(metadata: dict[str, Any]) -> bool:
    """Decide whether a streamed token belongs in the chat window.

    Two things must be excluded. The supervisor's own tool-calling turns emit no
    text, so they fall out naturally. A subagent's tokens do not: they are
    produced by a graph invoked inside a tool body, and they would stream a
    planning agent's internal reasoning into the user's chat. Those runs carry a
    checkpoint namespace nested under ``tools``, which is what distinguishes them.

    Args:
        metadata: Stream metadata for one token.

    Returns:
        ``True`` when the token is the supervisor writing its answer.
    """
    if metadata.get("langgraph_node") != "model":
        return False
    return "tools" not in str(metadata.get("langgraph_checkpoint_ns", ""))


def _is_affirmative(answer: object) -> bool:
    """Decide whether the user approved the pending save.

    Defaults to **no**. Anything not recognised as approval — silence, a
    question, a request to change something else — leaves the stored plan alone.
    A gate that resolves ambiguity in favour of proceeding is not a gate, and the
    cost of guessing wrong here is overwriting a plan the user was happy with.

    Args:
        answer: Whatever the user sent to resume the interrupt.

    Returns:
        ``True`` only on a recognised affirmative.
    """
    if isinstance(answer, bool):
        return answer
    if not isinstance(answer, str):
        return False

    normalised = answer.strip().lower().rstrip(".!")
    if normalised in _AFFIRMATIVE:
        return True
    # A short reply that opens with an affirmative ("yes please", "ok, do it").
    # Anything longer is prose that may well be a question, so it is not taken as
    # consent. The leading word is stripped of trailing punctuation, or the comma
    # in "ok, do it" makes a plain approval read as a decline.
    words = normalised.split()
    return bool(words) and len(words) <= 3 and words[0].rstrip(",;:") in _AFFIRMATIVE


def _to_langchain(messages: list[Message]) -> list[BaseMessage]:
    """Convert API messages into graph messages.

    Only user messages are fed in. Replaying stored assistant turns would
    duplicate them against what the checkpointer already holds.

    Args:
        messages: Messages from the request body.

    Returns:
        The user messages as LangChain messages.
    """
    return [HumanMessage(content=m.content) for m in messages if m.role == "user"]


agent = LangGraphAgent()

__all__ = ["DECLINED_MESSAGE", "GRAPH_NAME", "LangGraphAgent", "agent"]
