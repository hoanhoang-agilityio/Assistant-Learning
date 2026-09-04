"""The ``user_agent`` node: a tool-using agent that reads and writes the user's profile."""

from functools import lru_cache
from typing import NotRequired, TypedDict

from langchain.agents import create_agent
from langchain.agents.middleware import HumanInTheLoopMiddleware, InterruptOnConfig
from langchain.agents.middleware.types import ToolCallRequest
from langchain_core.messages import AIMessage, AnyMessage, ToolMessage
from langgraph.graph.state import CompiledStateGraph

from src.enums import UserAgentRoute
from src.prompts import USER_AGENT_SYSTEM
from src.schemas import GraphState, ProfileStatus, UserAgentContext, UserOutcome
from src.services.llm import RETRYABLE_ERRORS, agent_middleware, chat_model
from src.services.profile import load_profile, missing_profile_fields
from src.services.profile_presentation import PROFILE_UPDATED, update_summary
from src.tools import USER_AGENT_TOOLS, get_user_profile, update_user_profile

USER_AGENT_NAME = "user_agent"

USER_AGENT_FAILED = (
    "I could not get to your profile just now. Ask me again in a moment."
)


class UserAgentUpdate(TypedDict):
    """The state ``user_agent`` writes."""

    profile: dict | None
    profile_status: NotRequired[ProfileStatus | None]
    user_outcome: NotRequired[UserOutcome | None]
    messages: list[AnyMessage]


def _is_blank(value: object) -> bool:
    """Report whether a stored field carries no usable value."""
    if value is None:
        return True
    return isinstance(value, str) and not value.strip()


def _proposed_update(tool_call: dict) -> dict:
    """The change one ``update_user_profile`` call proposes, as a field-to-value mapping."""
    args = tool_call["args"]
    return {args["field"]: args.get("value")} if args.get("field") else {}


def _overwrites_a_stored_value(request: ToolCallRequest) -> bool:
    """Interrupt only when the field ``update_user_profile`` is about to write already has a value."""
    profile = request.runtime.context.profile or {}
    field = request.tool_call["args"].get("field")
    return not _is_blank(profile.get(field))


def _approval_question(tool_call: dict, _state: object, _runtime: object) -> str:
    """What the user is asked to approve: the change itself, not the call that would make it."""
    return update_summary(_proposed_update(tool_call))


@lru_cache
def build_user_agent() -> CompiledStateGraph:
    """Build the user agent once, with its profile tools bound."""

    return create_agent(
        model=chat_model(),
        tools=USER_AGENT_TOOLS,
        middleware=[
            *agent_middleware(),
            HumanInTheLoopMiddleware(
                interrupt_on={
                    update_user_profile.name: InterruptOnConfig(
                        allowed_decisions=["approve", "reject"],
                        description=_approval_question,
                        when=_overwrites_a_stored_value,
                    )
                }
            ),
        ],
        system_prompt=USER_AGENT_SYSTEM,
        context_schema=UserAgentContext,
        name=USER_AGENT_NAME,
    )


def _final_reply(messages: list[AnyMessage]) -> str | None:
    """The agent's own last word, which becomes the turn's reply when it wrote nothing."""

    for message in reversed(messages):
        if isinstance(message, AIMessage) and isinstance(message.content, str):
            reply = message.content.strip()
            if reply:
                return reply

    return None


def _tool_artifact(messages: list[AnyMessage], name: str) -> dict | None:
    """The artifact of the most recent call to one tool, if it was called this turn."""

    for message in reversed(messages):
        if isinstance(message, ToolMessage) and message.name == name:
            return message.artifact if isinstance(message.artifact, dict) else None

    return None


def _updated_profile(messages: list[AnyMessage]) -> dict | None:
    """The profile ``update_user_profile``'s direct write, or ``get_user_profile``'s read, left current."""

    for name in (update_user_profile.name, get_user_profile.name):
        artifact = _tool_artifact(messages, name)
        if artifact and isinstance(artifact.get("profile"), dict):
            return artifact["profile"]

    return None


def _wrote_profile(messages: list[AnyMessage]) -> bool:
    """Whether the agent actually saved a field this turn, rather than only reading one."""

    artifact = _tool_artifact(messages, update_user_profile.name)

    return bool(artifact) and artifact.get("status") == "written"


def _profile_completion_update(
    profile: dict | None, plan_pending: bool
) -> UserAgentUpdate:
    """Whether this turn's profile satisfies the plan that sent the caller here, when one did.

    Only computed when a plan is actually waiting on it — an ad-hoc question or edit must
    not trigger the onboarding form for a plan nobody asked to continue.
    """

    if not plan_pending:
        return {}
    if missing_profile_fields(profile):
        return {"profile_status": "need_input"}
    return {"profile_status": "ready"}


def _user_outcome(profile_status: ProfileStatus | None) -> UserOutcome:
    """What the supervisor reads off this turn"""

    return "needs_input" if profile_status == "need_input" else "answered"


def _failed(profile: dict | None, plan_pending: bool) -> UserAgentUpdate:
    """A turn the agent could not finish, reported as an outcome rather than left blank.

    A waiting plan whose fields are still missing is not a dead end — the form collects
    them without the model — so that turn reports what the form is about to do instead.
    """

    completion = _profile_completion_update(profile, plan_pending)

    if completion.get("profile_status") == "need_input":
        return {
            "profile": profile,
            "user_outcome": "needs_input",
            "messages": [],
            **completion,
        }

    return {
        "profile": profile,
        "user_outcome": "failed",
        "messages": [AIMessage(content=USER_AGENT_FAILED)],
        **completion,
    }


async def user_agent(state: GraphState) -> UserAgentUpdate:
    """Read or write the user's profile, pausing for the user's approval on an overwrite."""

    user_id = state["user_id"]
    profile = await load_profile(user_id)
    plan_pending = state.get("profile_status") == "need_input"

    # Only the transient failures the retry policy already gave up on: those leave the
    # profile reachable next turn. Anything else — a bad request, a bug, the approval
    # interrupt itself — is left to bubble, so the graph sees it rather than a blank turn.
    try:
        result = await build_user_agent().ainvoke(
            {"messages": state["messages"]},
            context=UserAgentContext(user_id=user_id, profile=profile),
        )
    except RETRYABLE_ERRORS:
        return _failed(profile, plan_pending)

    messages = result.get("messages", [])
    reply = PROFILE_UPDATED if _wrote_profile(messages) else _final_reply(messages)

    # The agent ran but came back with nothing to say and nothing written — a hit call
    # limit, an empty completion. There is no reply to show, so it is not an answer.
    if reply is None:
        return _failed(profile, plan_pending)

    updated_profile = _updated_profile(messages) or profile
    completion = _profile_completion_update(updated_profile, plan_pending)

    return {
        "profile": updated_profile,
        "user_outcome": _user_outcome(completion.get("profile_status")),
        "messages": [AIMessage(content=reply)],
        **completion,
    }


def route_after_user_agent(state: GraphState) -> UserAgentRoute:
    """Send the caller on to the profile form if a waiting plan still needs fields, or back to the supervisor."""

    if state.get("profile_status") == "need_input":
        return UserAgentRoute.NEEDS_MORE_INFO
    return UserAgentRoute.DONE
