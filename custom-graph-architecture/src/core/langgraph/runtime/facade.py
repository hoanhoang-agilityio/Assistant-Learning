"""The public facade the chat API depends on: compile the graph once, run one turn at a time."""

from collections.abc import AsyncGenerator
from time import perf_counter
from typing import Any

from langchain_core.messages import AIMessage, BaseMessage
from langchain_core.runnables import RunnableConfig
from langgraph.graph.state import CompiledStateGraph
from langgraph.types import Command

from src.constants import STEP_LABELS
from src.core.langgraph.graph import build_graph
from src.core.langgraph.runtime import graph_runtime
from src.core.observability.tracing import build_run_config
from src.enums import Node, StreamEventType
from src.schemas import Message, StreamResponse, initial_state
from src.utils.logging import bind_context, logger

_EXPORTABLE_ROLES = {"user", "assistant", "system"}

# What a finished turn reports about itself, read from the state the run settled on.
# Every one of these is a number the run is judged by, so they belong on one line rather
# than scattered across the node lines the turn happened to produce.
_TURN_OUTCOME_FIELDS = (
    "intent",
    "guard_blocked",
    "faithfulness_score",
    "coach_retry_count",
    "qa_retry_count",
    "hitl_retry_count",
    "user_info_retry_count",
    "hitl_decision",
)


class LangGraphRuntime:
    """Expose the compiled workflow graph through the chat API."""

    def __init__(self) -> None:
        """Prepare the lazily-compiled graph."""
        self._graph: CompiledStateGraph | None = None

    async def _get_graph(self) -> CompiledStateGraph:
        """Compile the graph against the shared checkpointer, once."""
        if self._graph is None:
            checkpointer = await graph_runtime.checkpointer()
            self._graph = build_graph().compile(checkpointer=checkpointer)
        return self._graph

    async def get_response(
        self, messages: list[Message], session_id: str, user_id: str
    ) -> list[Message]:
        """Process one turn and return the messages it produced."""
        graph = await self._get_graph()
        config, started = self._start_turn(session_id, user_id)
        run_input, before = await self._graph_input(graph, config, messages, user_id)
        try:
            await graph.ainvoke(run_input, config)
        except Exception as error:
            logger.exception(
                "graph_invoke_failed",
                session_id=session_id,
                duration_ms=_elapsed_ms(started),
                error=str(error),
            )
            raise
        return await self._finish_turn(graph, config, before, started)

    async def get_stream_response(
        self, messages: list[Message], session_id: str, user_id: str
    ) -> AsyncGenerator[StreamResponse]:
        """Process one turn, reporting each step as it is reached and then the replies."""
        graph = await self._get_graph()
        config, started = self._start_turn(session_id, user_id)
        run_input, before = await self._graph_input(graph, config, messages, user_id)
        try:
            async for update in graph.astream(run_input, config, stream_mode="updates"):
                for step in _step_events(update):
                    yield step
        except Exception as error:
            logger.exception(
                "graph_stream_failed",
                session_id=session_id,
                duration_ms=_elapsed_ms(started),
                error=str(error),
            )
            raise
        for reply in await self._finish_turn(graph, config, before, started):
            yield StreamResponse(type=StreamEventType.MESSAGE, content=reply.content)

    async def get_chat_history(self, session_id: str) -> list[Message]:
        """Return the conversation recorded for a session."""
        graph = await self._get_graph()
        state = await graph.aget_state({"configurable": {"thread_id": session_id}})
        return _to_chat_messages(state.values.get("messages", []))

    async def clear_chat_history(self, session_id: str) -> None:
        """Delete every checkpoint row for a session."""
        checkpointer = await graph_runtime.checkpointer()
        await checkpointer.adelete_thread(session_id)

    async def _graph_input(
        self,
        graph: CompiledStateGraph,
        config: RunnableConfig,
        messages: list[Message],
        user_id: str,
    ) -> tuple[Any, int]:
        """Decide whether this turn starts a run or resumes a paused one."""
        state = await graph.aget_state(config)
        reply = _latest_user_text(messages)
        before = len(state.values.get("messages", []))
        if state.next:
            return Command(resume=reply), before
        return initial_state(reply, user_id), before

    def _start_turn(
        self, session_id: str, user_id: str
    ) -> tuple[RunnableConfig, float]:
        """Open one turn: its run config, its log correlation and its latency clock."""
        config = build_run_config(session_id, user_id)
        # Bound here rather than in the middleware because run_id is per turn, not per
        # request: it is what stitches a turn's node lines back to its trace.
        bind_context(run_id=config["metadata"]["run_id"])
        return config, perf_counter()

    async def _finish_turn(
        self,
        graph: CompiledStateGraph,
        config: RunnableConfig,
        before: int,
        started: float,
    ) -> list[Message]:
        """Read the turn's replies off the settled state, and log what it came to."""
        state = await graph.aget_state(config)
        replies = _turn_reply(state, before)
        logger.info(
            "turn_completed",
            duration_ms=_elapsed_ms(started),
            paused=bool(state.next),
            reply_count=len(replies),
            final_message=state.values.get("final_message"),
            **{
                field: state.values.get(field)
                for field in _TURN_OUTCOME_FIELDS
                if state.values.get(field) is not None
            },
        )
        return replies


def _elapsed_ms(started: float) -> float:
    """Milliseconds since a ``perf_counter`` reading."""
    return round((perf_counter() - started) * 1000, 2)


def _turn_reply(state: Any, before: int) -> list[Message]:
    """Read what the graph said back this turn, plus the question a fresh pause is asking.

    Only assistant-authored messages: a fresh top-level turn is invoked with
    the user's own message as part of its input, so it lands in
    ``messages[before:]`` too, alongside any ``HumanMessage`` a resumed
    interrupt records for the decision it just read.

    The question a pause is asking is usually already one of those replies — the node
    before the gate writes it into the conversation so it survives a reload — so it is
    appended only when nothing already carries it.
    """
    new_messages = _to_chat_messages(state.values.get("messages", [])[before:])
    replies = [message for message in new_messages if message.role == "assistant"]
    pending = _pending_interrupt_value(state)
    if pending is not None:
        question = _interrupt_text(pending)
        if question and not any(question in reply.content for reply in replies):
            replies.append(Message(role="assistant", content=question))
    return replies


def _step_events(update: Any) -> list[StreamResponse]:
    """Name the nodes one superstep finished, for the caller to show as progress."""
    if not isinstance(update, dict):
        return []

    events: list[StreamResponse] = []
    for name in update:
        try:
            label = STEP_LABELS.get(Node(name))
        except ValueError:
            continue
        if label:
            events.append(
                StreamResponse(type=StreamEventType.STEP, node=name, label=label)
            )
    return events


def _pending_interrupt_value(state: Any) -> object | None:
    """Return the payload of an interrupt the run is parked at."""
    if not state.next or not state.tasks:
        return None
    for task in state.tasks:
        if task.interrupts:
            return task.interrupts[0].value
    return None


def _interrupt_text(value: object) -> str:
    """Render an interrupt payload as the question to show the user."""
    if isinstance(value, dict):
        return str(value.get("message", ""))
    return str(value)


def _latest_user_text(messages: list[Message]) -> str:
    """Return the newest user message's content, which is what one turn sends."""
    return next((m.content for m in reversed(messages) if m.role == "user"), "")


def _role_of(message: BaseMessage) -> str:
    """Map a LangChain message type to a chat role."""
    if isinstance(message, AIMessage):
        return "assistant"
    return {"human": "user", "ai": "assistant", "system": "system"}.get(
        message.type, message.type
    )


def _message_text(message: BaseMessage) -> str:
    """Extract plain text from a message whose content may be a block list."""
    content = message.content
    if isinstance(content, str):
        return content
    return "".join(
        block.get("text", "")
        for block in content
        if isinstance(block, dict) and block.get("type") == "text"
    )


def _to_chat_messages(messages: list[BaseMessage]) -> list[Message]:
    """Convert graph messages into the API's response schema."""
    result: list[Message] = []
    for message in messages:
        role = _role_of(message)
        text = _message_text(message)
        if role in _EXPORTABLE_ROLES and text:
            result.append(Message(role=role, content=text))
    return result


langgraph_runtime = LangGraphRuntime()

__all__ = ["LangGraphRuntime", "langgraph_runtime"]
