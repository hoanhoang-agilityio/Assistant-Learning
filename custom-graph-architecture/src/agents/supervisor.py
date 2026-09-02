"""The ``supervisor`` node: decides one agent at a time, in a loop, until it decides FINISH."""

from typing import TypedDict

from langchain_core.messages import SystemMessage
from pydantic import BaseModel, Field

from src.enums import SupervisorRoute
from src.schemas import GraphState, NextAgent
from src.services.llm import chat_model, with_retry_policy

SUPERVISOR_MAX_ITERATIONS = 8

SUPERVISOR_SYSTEM = """
You route one user request at a time to the agent that should handle it next.

## Agents
- `user_agent`: reads or writes the user's own profile — a question about their stored
  data, or a new or corrected fact about themselves.
- `coach_agent`: the user's training plan — a question about the plan on record, or a
  request to build or revise one. It reads the stored plan itself, so a question about
  the plan goes here rather than being answered from the conversation.
- `qa_agent`: answers a training, nutrition or injury knowledge question.
- `FINISH`: nothing is left to do; the conversation's last message is the reply.

## Rules
1. Read the conversation and decide what, if anything, is still unaddressed.
2. A request for a plan goes to `coach_agent` first, even when the user states their own
   details in the same message — it is the one that knows whether its profile is complete
   enough to plan with. When `profile_status` reads `need_input`, route to `user_agent` to
   collect what is missing; once it reads `ready`, continue the plan already in progress
   with `coach_agent` rather than asking again.
3. When a request has more than one part, resolve a `qa_agent` part before a part that
   ends in an approval interrupt (a plan through `coach_agent`, or a profile overwrite
   through `user_agent`) — otherwise the interrupt splits the request across two user
   turns.
4. Do not choose `FINISH` while any part of the user's request is still unaddressed.
5. Choose `FINISH` once every part has been handled, including a question you can
   already answer from the conversation itself.
"""


class SupervisorDecision(BaseModel):
    """The supervisor's structured routing decision."""

    next: NextAgent = Field(description="The agent to run next, or FINISH.")


class SupervisorUpdate(TypedDict):
    """The state ``supervisor`` writes."""

    next: NextAgent
    iteration_count: int


def _profile_status_line(state: GraphState) -> str | None:
    """Relay ``profile_status`` to the model as one line — set by coach/user_agent, never recomputed here."""

    status = state.get("profile_status")
    if status is None:
        return None
    return f"profile_status: {status}"


async def supervisor(state: GraphState) -> SupervisorUpdate:
    """Decide which agent runs next, or that the turn is done."""

    iteration_count = state.get("iteration_count", 0) + 1
    if iteration_count > SUPERVISOR_MAX_ITERATIONS:
        return {"next": "FINISH", "iteration_count": iteration_count}

    model = with_retry_policy(chat_model().with_structured_output(SupervisorDecision))

    context = [SystemMessage(content=SUPERVISOR_SYSTEM)]
    status_line = _profile_status_line(state)
    if status_line:
        context.append(SystemMessage(content=status_line))

    try:
        decision = await model.ainvoke([*context, *state["messages"]])
    except Exception:
        return {"next": "FINISH", "iteration_count": iteration_count}

    return {"next": decision.next, "iteration_count": iteration_count}


def route_after_supervisor(state: GraphState) -> SupervisorRoute:
    """Dispatch on the supervisor's own routing decision."""

    return SupervisorRoute(state["next"])
