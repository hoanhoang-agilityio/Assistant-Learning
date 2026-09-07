"""The ``supervisor`` node: decides one agent at a time, in a loop, until it decides FINISH."""

from typing import TypedDict

from langchain_core.messages import AnyMessage, HumanMessage, SystemMessage
from pydantic import BaseModel, Field

from src.agents.history import trim_history
from src.enums import SupervisorRoute
from src.schemas import GraphState, NextAgent
from src.services.llm import chat_model, with_retry_policy

SUPERVISOR_MAX_ITERATIONS = 8

ROUTING_STATE_FIELDS = ("profile_status", "user_outcome",
                        "coach_outcome", "qa_outcome")

SUPERVISOR_SYSTEM = """
You route one user request at a time to the agent that should handle it next.

## Agents

- `user_agent`: reads or writes the user's own profile — a question about their stored
  data, or a new or corrected fact about themselves.

- `coach_agent`: handles the user's training plan — a question about the plan on record,
  or a request to build or revise one. It reads the stored plan itself.

- `qa_agent`: answers training, nutrition, or injury knowledge questions.

- `FINISH`: nothing is left to do; the conversation's last message is the reply.

## What you are shown

The conversation below is the user's own turns only. The agents' replies are not in it:
what each of them came to is reported in the workflow state instead. An agent whose
outcome appears in that state has already answered the user, even though you cannot see
the answer. Never route to an agent to produce a reply the state says it produced.

## Workflow state

- `profile_status`
  - `need_input`: a plan is waiting on profile fields that are still missing.
  - `ready`: the profile fields a plan requires are all on record.

- `user_outcome`
  - `answered`: `user_agent` has handled the profile part of this request.
  - `needs_input`: it ran, and the fields still missing are being collected by the form.
  - `failed`: it could not finish and has told the user so. That part is over for this
    turn; running it again produces the same failure.

- `coach_outcome`
  - `answered`: it answered a question about the plan on record.
  - `drafted`: it built or revised the plan and the user has been shown the result.
  - `needs_profile`: it cannot plan until the profile is complete, so the plan is still
    in progress rather than finished.

- `qa_outcome`
  - `answered`: `qa_agent` answered the knowledge question.
  - `fallback`: it could not ground an answer and has told the user so. That part is
    finished; asking again produces the same result.

## Rules

1. Read the user's request and determine what, if anything, is still unaddressed.

2. A request for a plan goes to `coach_agent` first, even when the user states their
   own profile details in the same message. `coach_agent` determines whether the
   profile is complete enough to proceed.

3. If `profile_status` is `need_input`, route to `user_agent` to collect what is missing.

4. If `coach_outcome` is `needs_profile` and `profile_status` is `ready`, continue the
   plan already in progress with `coach_agent`. Do not ask for the profile again.

5. `user_outcome` of `answered` or `failed` means the profile part is over for this
   turn — handled, or failed in a way that running it again will not fix. Do not route
   to `user_agent` again unless the user asked for a further profile change.

6. `coach_outcome` of `answered` or `drafted` means the coaching part has been handled.
   Do not route to `coach_agent` again unless the user asked for further coaching work.

7. `qa_outcome` of `answered` or `fallback` means the knowledge part has been handled.
   Do not route to `qa_agent` again unless the user asked a second, different question.

8. When a request has multiple parts, resolve a `qa_agent` part before a part that
   ends in an approval interrupt (a plan through `coach_agent`, or a profile overwrite
   through `user_agent`) so that the interrupt does not split the request across
   multiple user turns.

9. Do not choose `FINISH` while any part of the user's request is still unaddressed.

10. Choose `FINISH` once every part of the request has an outcome in the workflow state.

11. Never route to an agent solely because that agent handled the previous step, and
    never route to one to check or repeat work the state already reports as done.
"""


class SupervisorDecision(BaseModel):
    """The supervisor's structured routing decision."""

    next: NextAgent = Field(description="The agent to run next, or FINISH.")


class SupervisorUpdate(TypedDict):
    """The state ``supervisor`` writes."""

    next: NextAgent
    iteration_count: int


def _routing_state_line(state: GraphState) -> str | None:
    """Expose the agents' status signals, and none of the data they were derived from."""

    lines = [
        f"{field}: {state[field]}"
        for field in ROUTING_STATE_FIELDS
        if state.get(field) is not None
    ]

    return "\n".join(lines) or None


def _routing_history(state: GraphState) -> list[AnyMessage]:
    """The user's own turns."""

    return trim_history(
        [message for message in state["messages"]
            if isinstance(message, HumanMessage)]
    )


async def supervisor(state: GraphState) -> SupervisorUpdate:
    """Decide which agent runs next, or that the turn is done."""
    iteration_count = state.get("iteration_count", 0) + 1

    if iteration_count > SUPERVISOR_MAX_ITERATIONS:
        return {"next": "FINISH", "iteration_count": iteration_count}

    history = _routing_history(state)

    if not history:
        return {"next": "FINISH", "iteration_count": iteration_count}

    model = with_retry_policy(
        chat_model().with_structured_output(SupervisorDecision))

    context = [SystemMessage(content=SUPERVISOR_SYSTEM)]

    routing_state = _routing_state_line(state)

    if routing_state:
        context.append(
            SystemMessage(content=f"Current workflow state:\n{routing_state}")
        )

    try:
        decision = await model.ainvoke([*context, *history])
    except Exception:
        return {
            "next": "FINISH",
            "iteration_count": iteration_count,
        }

    return {
        "next": decision.next,
        "iteration_count": iteration_count,
    }


def route_after_supervisor(state: GraphState) -> SupervisorRoute:
    """Dispatch on the supervisor's own routing decision."""

    return SupervisorRoute(state["next"])
