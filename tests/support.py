"""Helpers for exercising tools without standing up an agent around them.

Under the supervisor architecture the guarantees that used to be graph edges
live inside tool bodies, so that is where the tests have to reach. A tool is an
ordinary function underneath its ``@tool`` decorator; what it needs that a plain
call does not supply is a :class:`ToolRuntime` — the state, the config and the
id of the call being answered.

Building one here rather than driving a whole agent is what keeps these tests
assertions about the tool's own contract instead of about a model's willingness
to call it.
"""

from typing import Any

from langchain.tools import ToolRuntime
from langchain_core.messages import ToolMessage
from langgraph.types import Command


def runtime(state: dict[str, Any], config: dict[str, Any] | None = None) -> ToolRuntime:
    """Build a tool runtime around a state dict.

    Args:
        state: What the tool will read as the agent's state.
        config: Runnable config, carrying ``metadata`` and ``configurable``.

    Returns:
        A runtime a tool body can be called with directly.
    """
    return ToolRuntime(
        state=state,
        context=None,
        config=config or {},
        stream_writer=lambda _chunk: None,
        tool_call_id="test_call",
        store=None,
    )


def call(tool: Any, state: dict[str, Any], config: dict | None = None, **kwargs: Any) -> Any:
    """Invoke a tool's body directly, bypassing the model that would call it.

    Args:
        tool: The decorated tool.
        state: State to expose through the runtime.
        config: Runnable config for the call.
        **kwargs: The tool's own arguments.

    Returns:
        Whatever the tool returns — a string, or a ``Command``. Coroutines are
        returned unawaited so an async test can await them.
    """
    body = tool.coroutine or tool.func
    return body(runtime=runtime(state, config), **kwargs)


def updates(result: Command) -> dict[str, Any]:
    """Read the state a tool wrote, without the message it wrote alongside.

    Args:
        result: What the tool returned.

    Returns:
        The state update, minus ``messages``.
    """
    return {key: value for key, value in result.update.items() if key != "messages"}


def message(result: Command) -> ToolMessage:
    """Read the tool result the model would have seen.

    Args:
        result: What the tool returned.

    Returns:
        The single ``ToolMessage`` the command carries.
    """
    return result.update["messages"][0]


__all__ = ["call", "message", "runtime", "updates"]
