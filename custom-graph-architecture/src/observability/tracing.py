"""The ``RunnableConfig`` for one graph run."""

from uuid import uuid4

from langchain_core.callbacks import BaseCallbackHandler
from langchain_core.runnables import RunnableConfig

from src.configs.config import settings
from src.observability.langfuse import get_langfuse_callbacks

TURN_TRACE_NAME = "chat_turn"


def build_run_config(
    session_id: str,
    user_id: str,
    run_id: str | None = None,
) -> RunnableConfig:
    """Assemble the run config for one turn.

    Args:
        session_id: Conversation thread. Keys the checkpoint lineage and the trace session.
        user_id: Owner of the run.
        run_id: Correlation id for this turn. Generated when not supplied.

    Returns:
        RunnableConfig: Config with the checkpoint thread, the shared Langfuse handler and
        the trace metadata.
    """
    callbacks: list[BaseCallbackHandler] = get_langfuse_callbacks()
    return {
        "configurable": {"thread_id": session_id},
        "callbacks": callbacks,
        # Without a name every trace is titled after the compiled graph, so a list of
        # runs reads as one repeated string and nothing is findable by what it was.
        "run_name": TURN_TRACE_NAME,
        "tags": [settings.ENVIRONMENT.value],
        "metadata": {
            # The langfuse_-prefixed keys are the only ones the LangChain integration
            # promotes to the trace's own session/user fields. Without them the values
            # are stored as plain metadata and the trace is not filterable by either.
            "langfuse_session_id": session_id,
            "langfuse_user_id": user_id,
            # Read by the Langfuse callback handler itself (not just stored): a HITL
            # turn pauses mid-trace on a GraphInterrupt, and the resume arrives as a
            # brand-new root run. Without this key the handler can't tell it apart from
            # an unrelated run on the same thread, and opens a second trace instead of
            # reattaching to the one that paused.
            "thread_id": session_id,
            "run_id": run_id or str(uuid4()),
            "user_id": user_id,
            "session_id": session_id,
            "environment": settings.ENVIRONMENT.value,
            "debug": settings.DEBUG,
        },
    }
