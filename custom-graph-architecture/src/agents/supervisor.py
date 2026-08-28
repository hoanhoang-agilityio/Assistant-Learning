"""The ``supervisor`` node: decides one agent at a time, in a loop, until it decides FINISH."""

from typing import TypedDict

from langchain_core.messages import SystemMessage
from pydantic import BaseModel, Field

from src.core.llm import chat_model, with_retry_policy
from src.enums import SupervisorRoute
from src.schemas import GraphState, NextAgent

SUPERVISOR_MAX_ITERATIONS = 8

SUPERVISOR_SYSTEM = """
You route one user request at a time to the agent that should handle it next.

## Agents
- `user_agent`: reads or writes the user's own profile — a question about their stored
  data, or a new or corrected fact about themselves.
- `coach_agent`: builds or revises the user's training plan.
- `qa_agent`: answers a training, nutrition or injury knowledge question.
- `FINISH`: nothing is left to do; the conversation's last message is the reply.

## Rules
1. Read the conversation and decide what, if anything, is still unaddressed.
2. When a request has more than one part, resolve a `qa_agent` part before a part that
   ends in an approval interrupt (a plan through `coach_agent`, or a profile overwrite
   through `user_agent`) — otherwise the interrupt splits the request across two user
   turns.
3. Do not choose `FINISH` while any part of the user's request is still unaddressed.
4. Choose `FINISH` once every part has been handled, including a question you can
   already answer from the conversation itself.
"""


class SupervisorDecision(BaseModel):
    """The supervisor's structured routing decision."""

    next: NextAgent = Field(description="The agent to run next, or FINISH.")


class SupervisorUpdate(TypedDict):
    """The state ``supervisor`` writes."""

    next: NextAgent
    iteration_count: int


async def supervisor(state: GraphState) -> SupervisorUpdate:
    """Decide which agent runs next, or that the turn is done."""

    iteration_count = state.get("iteration_count", 0) + 1
    if iteration_count > SUPERVISOR_MAX_ITERATIONS:
        return {"next": "FINISH", "iteration_count": iteration_count}

    model = with_retry_policy(chat_model().with_structured_output(SupervisorDecision))

    try:
        decision = await model.ainvoke(
            [SystemMessage(content=SUPERVISOR_SYSTEM), *state["messages"]]
        )
    except Exception:
        return {"next": "FINISH", "iteration_count": iteration_count}

    return {"next": decision.next, "iteration_count": iteration_count}


def route_after_supervisor(state: GraphState) -> SupervisorRoute:
    """Dispatch on the supervisor's own routing decision."""

    return SupervisorRoute(state["next"])
