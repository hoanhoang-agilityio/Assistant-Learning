"""The supervisor: the model that decides what happens on a turn.

Replaces four root nodes — ``classify``, ``intent_branch``, ``verdict_gate`` and
``compose_answer`` — and, with them, the idea that the order of steps is a
property of the graph. It is now a decision the model re-makes after every tool
result, which is what buys the three things a router cannot do: handle a turn
with two intents, recover from its own bad first guess, and ask a follow-up
without ending the turn (``docs/supervisor-architecture.md`` §4, §13).

What that costs is paid back in the two places a guarantee can still live. Steps
that must run every turn are middleware, which compiles to real nodes the model
cannot skip. Steps that are conditions on being allowed to proceed are
preconditions inside tool bodies, returning a refusal the model can read but not
route around.

The confirm gate is ``HumanInTheLoopMiddleware``, and it interrupts on a **tool
name** rather than on a model's judgment about whether this change is
significant. That distinction is the whole gate: the old ``confirm`` node could
not be reasoned past, and neither can this one.
"""

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

from app.core.langgraph import drafts
from app.core.langgraph.models import default_model, resilience_middleware
from app.core.langgraph.supervisor.middleware import middleware as spine
from app.core.langgraph.supervisor.state import SupervisorState
from app.core.langgraph.supervisor.tools import tools

AGENT_NAME = "supervisor"

# Model calls one turn may cost. A turn with two intents legitimately runs three
# or four hops — plan, then answer the question about it, then write the reply —
# and this is the ceiling under all of them. It replaces `recursion_limit`, which
# fails the turn with a stack trace; `end` stops cleanly with whatever has been
# written.
_MAX_MODEL_CALLS = 8

# Approve or reject only. `edit` would let the confirm gate hand back changed
# arguments — a different `draft_id` — which is exactly the substitution the
# draft store exists to prevent. `respond` would answer on the tool's behalf,
# which for a save means telling the model a plan was stored when none was.
_SAVE_DECISIONS = ["approve", "reject"]


def _save_description(tool_call: ToolCall, state: SupervisorState, runtime: Runtime) -> str:
    """Render the question the user is asked before a plan is saved.

    Read from the draft, never from the tool call's arguments beyond the handle.
    The diff, the verdict and the findings are what was verified; a question
    assembled from what the model typed would be a question about a different
    plan than the one about to be stored.

    Args:
        tool_call: The pending ``save_plan`` call.
        state: Current supervisor state. Unused — the draft carries everything.
        runtime: Agent runtime. Unused.

    Returns:
        The question to put to the user.
    """
    draft = drafts.read(str(tool_call["args"].get("draft_id", "")))
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


def build_supervisor() -> CompiledStateGraph:
    """Build the supervisor, uncompiled — the caller attaches the checkpointer.

    The checkpointer is not attached here because it is a resource the facade
    owns and opens lazily, and because a second one anywhere in the tree writes a
    competing history.

    Returns:
        The compiled supervisor, named so its spans are identifiable in Langfuse.
    """
    return build_supervisor_with(checkpointer=None)


def build_supervisor_with(checkpointer: Any) -> CompiledStateGraph:
    """Build the supervisor against a specific checkpointer.

    Args:
        checkpointer: The checkpointer to persist the whole tree with, or
            ``None`` for an unpersisted conversation.

    Returns:
        The compiled supervisor.
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

    Args:
        value: Whatever the middleware passed to ``interrupt()``.

    Returns:
        Text to send to the user.
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
    "build_supervisor",
    "build_supervisor_with",
    "interrupt_question",
]
