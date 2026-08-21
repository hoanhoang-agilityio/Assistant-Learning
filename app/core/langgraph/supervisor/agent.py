"""The supervisor: the model that decides what happens on a turn."""

import json
from typing import Any

from langchain.agents import create_agent
from langchain.agents.middleware import (
    AgentMiddleware,
    HumanInTheLoopMiddleware,
    InterruptOnConfig,
    ModelCallLimitMiddleware,
)
from langchain_core.messages import ToolCall
from langgraph.graph.state import CompiledStateGraph
from langgraph.runtime import Runtime

from app.core.langgraph.runtime import draft_store
from app.core.langgraph.runtime.models import default_model, resilience_middleware
from app.core.langgraph.supervisor.middleware import middleware as spine
from app.core.langgraph.supervisor.state import SupervisorState
from app.core.langgraph.supervisor.tools import tools

AGENT_NAME = "supervisor"

_MAX_MODEL_CALLS = 8

_SAVE_DECISIONS = ["approve", "reject"]


def _save_description(tool_call: ToolCall, state: SupervisorState, runtime: Runtime) -> str:
    """Render the question the user is asked before a plan is saved.

    Read from the draft, never from the tool call's arguments beyond the handle.
    The diff, the verdict and the findings are what was verified; a question
    assembled from what the model typed would be a question about a different
    plan than the one about to be stored.

    """
    draft = draft_store.read(str(tool_call["args"].get("draft_id", "")))
    if draft is None:
        return "Save this plan? (The draft could not be read back — it may have expired.)"

    parts: list[str] = []
    if draft.diff:
        parts.append(str(draft.diff.get("summary") or "This will change your plan."))
    else:
        parts.append("This will become your plan.")

    parts.append(draft.plan_rendered)

    blocking = [issue for issue in draft.issues if issue["severity"] != "info"]
    if blocking:
        parts.append("Findings:\n" + "\n".join(f"- {issue['message']}" for issue in blocking))

    return "\n\n".join(parts)


def build_supervisor_with(checkpointer: Any) -> CompiledStateGraph:
    """Build the supervisor against a specific checkpointer.

    The checkpointer is passed in because it is a resource the facade owns and
    opens lazily, and because a second one anywhere in the tree writes a
    competing history. Pass ``None`` when persistence is not needed.

    Args:
        checkpointer: The LangGraph checkpointer, or ``None`` to compile without
            one (diagrams, tests that do not resume).

    Returns:
        The compiled supervisor, named so its spans are identifiable in Langfuse.
    """
    middleware: list[AgentMiddleware] = [
        *spine,
        *resilience_middleware(),
        HumanInTheLoopMiddleware(
            interrupt_on={
                "save_plan": InterruptOnConfig(
                    allowed_decisions=_SAVE_DECISIONS,
                    description=_save_description,
                )
            }
        ),
        ModelCallLimitMiddleware(run_limit=_MAX_MODEL_CALLS, exit_behavior="end"),
    ]

    return create_agent(
        model=default_model(),
        tools=tools,
        state_schema=SupervisorState,
        middleware=tuple(middleware),
        checkpointer=checkpointer,
        name=AGENT_NAME,
    )


def interrupt_question(value: object) -> str:
    """Render a pending interrupt as the message the user sees.

    The middleware's payload is structured so a UI can show the diff properly,
    but the chat surface must show the question — not the JSON around it.
    """
    if isinstance(value, str):
        return value

    if isinstance(value, dict):
        requests = value.get("action_requests")
        if isinstance(requests, list) and requests:
            described = [
                str(request.get("description") or f"Run {request.get('name')}?")
                for request in requests
                if isinstance(request, dict)
            ]
            if described:
                return "\n\n".join(described)
        if isinstance(value.get("question"), str):
            return value["question"]

    return json.dumps(value, ensure_ascii=False, default=str)


__all__ = [
    "AGENT_NAME",
    "build_supervisor_with",
    "interrupt_question",
]
