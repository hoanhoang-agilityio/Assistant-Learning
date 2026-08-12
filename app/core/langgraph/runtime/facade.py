"""The public facade the API depends on, and the resources it owns.

What is behind it changed completely; what it looks like did not. The API still
calls four methods, still does not know subgraphs exist, and still does not
assemble context — the supervisor loads its own, so a caller that is not this
facade is not a degraded caller.
"""

from collections.abc import AsyncGenerator
from typing import Any

from langchain_core.callbacks import BaseCallbackHandler
from langchain_core.messages import AIMessage, BaseMessage, HumanMessage
from langchain_core.runnables import RunnableConfig
from langgraph.graph.state import CompiledStateGraph
from langgraph.types import Command
from psycopg_pool import AsyncConnectionPool

from app.core.configs.config import Environment, settings
from app.core.langgraph.agents.registry import build_all
from app.core.langgraph.runtime.checkpointer import CheckpointerResources
from app.core.langgraph.runtime.messages import message_text, to_chat_messages
from app.core.langgraph.supervisor import build_supervisor_with, interrupt_question
from app.core.logging import logger
from app.core.observability import get_langfuse_callbacks
from app.schemas.chat import Message
from app.services.llm.service import llm_service

GRAPH_NAME = "supervisor"

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

DECLINED_MESSAGE = (
    "Left your plan as it was. Nothing has changed. Tell me if you want to try a "
    "different adjustment."
)


class LangGraphRuntime:
    """Expose the compiled supervisor through the application's chat API."""

    def __init__(self) -> None:
        """Prepare lazily-created resources."""
        self.llm_service = llm_service
        self._checkpointer_resources = CheckpointerResources()
        self._graph: CompiledStateGraph | None = None

    @property
    def _connection_pool(self) -> AsyncConnectionPool | None:
        """Expose the historical private pool attribute for compatibility."""
        return self._checkpointer_resources.connection_pool

    @_connection_pool.setter
    def _connection_pool(self, value: AsyncConnectionPool | None) -> None:
        self._checkpointer_resources.connection_pool = value

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
        return await self._checkpointer_resources.get_connection_pool()

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
            checkpointer = await self._checkpointer_resources.get_checkpointer()
            self._graph = build_supervisor_with(checkpointer)
            return self._graph
        except Exception as error:
            logger.exception("graph_creation_failed", error=str(error))
            if settings.ENVIRONMENT == Environment.PRODUCTION:
                return None
            raise

    async def _get_graph(self) -> CompiledStateGraph:
        """Return the compiled supervisor, building it on first use."""
        graph = await self.create_graph()
        if graph is None:
            raise RuntimeError("graph is unavailable — check the database connection")
        return graph

    async def get_response(
        self,
        messages: list[Message],
        session_id: str,
        user_id: str | None = None,
        username: str | None = None,
    ) -> list[Message]:
        """Process one turn and return the messages produced."""
        graph = await self._get_graph()
        config = self._build_config(session_id, user_id, username)
        try:
            await graph.ainvoke(await self._graph_input(graph, config, messages), config)
        except Exception as error:
            logger.exception("graph_invoke_failed", session_id=session_id, error=str(error))
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
        """Stream one turn as text chunks."""
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
        except Exception as error:
            logger.exception("graph_stream_failed", session_id=session_id, error=str(error))
            raise
        interrupt_message = await self._pending_interrupt(graph, config)
        if interrupt_message is not None:
            yield interrupt_message.content

    async def get_chat_history(self, session_id: str) -> list[Message]:
        """Return the conversation recorded for a session."""
        graph = await self._get_graph()
        state = await graph.aget_state({"configurable": {"thread_id": session_id}})
        return to_chat_messages(state.values.get("messages", []))

    async def clear_chat_history(self, session_id: str) -> None:
        """Delete every checkpoint row for a session."""
        await self._get_graph()
        await self._checkpointer_resources.clear_thread(session_id)

    def _build_config(
        self, session_id: str, user_id: str | None, username: str | None
    ) -> RunnableConfig:
        """Assemble the runnable config for one turn."""
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
        """Decide whether this turn starts a run or resumes a paused one."""
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
            {"type": "approve"} if approved else {"type": "reject", "message": DECLINED_MESSAGE}
        )
        return Command(resume={"decisions": [decision] * _pending_action_count(pending)})

    async def _pending_interrupt(
        self, graph: CompiledStateGraph, config: RunnableConfig
    ) -> Message | None:
        """Surface a confirm gate the run stopped at, if any."""
        state = await graph.aget_state(config)
        value = _pending_interrupt_value(state)
        if value is None:
            return None
        return Message(role="assistant", content=interrupt_question(value))

    async def _last_answer(self, graph: CompiledStateGraph, config: RunnableConfig) -> str:
        """Read the answer this turn produced out of the transcript."""
        state = await graph.aget_state(config)
        for message in reversed(state.values.get("messages", [])):
            if isinstance(message, AIMessage):
                return message_text(message)
        return ""


def _pending_interrupt_value(state: Any) -> object | None:
    """Return the payload of an interrupt the run is parked at."""
    if not state.next or not state.tasks:
        return None
    for task in state.tasks:
        if task.interrupts:
            return task.interrupts[0].value
    return None


def _pending_action_count(value: object) -> int:
    """Count the actions one interrupt is asking about."""
    if isinstance(value, dict):
        requests = value.get("action_requests")
        if isinstance(requests, list) and requests:
            return len(requests)
    return 1


def _is_supervisor_answer(metadata: dict[str, Any]) -> bool:
    """Decide whether a streamed token belongs in the chat window."""
    if metadata.get("langgraph_node") != "model":
        return False
    return "tools" not in str(metadata.get("langgraph_checkpoint_ns", ""))


def _is_affirmative(answer: object) -> bool:
    """Decide whether the user approved the pending save."""
    if isinstance(answer, bool):
        return answer
    if not isinstance(answer, str):
        return False
    normalised = answer.strip().lower().rstrip(".!")
    if normalised in _AFFIRMATIVE:
        return True
    words = normalised.split()
    return bool(words) and len(words) <= 3 and words[0].rstrip(",;:") in _AFFIRMATIVE


def _to_langchain(messages: list[Message]) -> list[BaseMessage]:
    """Convert API messages into graph messages."""
    return [HumanMessage(content=message.content) for message in messages if message.role == "user"]


LangGraphAgent = LangGraphRuntime
langgraph_runtime = LangGraphRuntime()
agent = langgraph_runtime

__all__ = [
    "DECLINED_MESSAGE",
    "GRAPH_NAME",
    "LangGraphAgent",
    "LangGraphRuntime",
    "agent",
    "langgraph_runtime",
]
