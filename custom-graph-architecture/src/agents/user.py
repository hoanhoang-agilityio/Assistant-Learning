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
from src.schemas import GraphState, ProfileRequiredFor, ProfileStatus, UserAgentContext
from src.services.llm import agent_middleware, chat_model
from src.services.profile import load_user_context, missing_profile_fields
from src.tools import USER_AGENT_TOOLS, get_user_profile, update_user_profile

USER_AGENT_NAME = "user_agent"


class UserAgentUpdate(TypedDict):
    """The state ``user_agent`` writes."""

    profile: dict | None
    profile_required_for: NotRequired[ProfileRequiredFor | None]
    profile_status: NotRequired[ProfileStatus | None]
    messages: list[AnyMessage]


def _is_blank(value: object) -> bool:
    """Report whether a stored field carries no usable value."""
    if value is None:
        return True
    return isinstance(value, str) and not value.strip()


def _overwrites_a_stored_value(request: ToolCallRequest) -> bool:
    """Interrupt only when the field ``update_user_profile`` is about to write already has a value."""
    profile = request.runtime.context.profile or {}
    field = request.tool_call["args"].get("field")
    return not _is_blank(profile.get(field))


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
    """The agent's own last word, which becomes the turn's reply."""

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


def _profile_completion_update(
    profile: dict | None, required_for: ProfileRequiredFor | None
) -> UserAgentUpdate:
    """Whether this turn's profile satisfies the plan that sent the caller here, when one did.

    Only computed when a plan is actually waiting on it — an ad-hoc question or edit must
    not trigger the onboarding form for a plan nobody asked to continue. Once the profile
    turns out complete, ``profile_required_for`` is cleared here too, so the router skips
    the form rather than sending the caller through it for nothing.
    """

    if required_for != "plan":
        return {}
    if missing_profile_fields(profile):
        return {"profile_status": "need_input"}
    return {"profile_status": "ready", "profile_required_for": None}


async def user_agent(state: GraphState) -> UserAgentUpdate:
    """Read or write the user's profile, pausing for the user's approval on an overwrite."""

    user_id = state["user_id"]
    profile = (await load_user_context(user_id)).profile
    required_for = state.get("profile_required_for")

    try:
        result = await build_user_agent().ainvoke(
            {"messages": state["messages"]},
            context=UserAgentContext(user_id=user_id, profile=profile),
        )
    except Exception:
        return {
            "profile": profile,
            "messages": [],
            **_profile_completion_update(profile, required_for),
        }

    messages = result.get("messages", [])
    reply = _final_reply(messages)
    updated_profile = _updated_profile(messages) or profile

    return {
        "profile": updated_profile,
        "messages": [AIMessage(content=reply)] if reply else [],
        **_profile_completion_update(updated_profile, required_for),
    }


def route_after_user_agent(state: GraphState) -> UserAgentRoute:
    """Send the caller on to the profile form if a waiting plan still needs fields, or back to the supervisor."""

    if (
        state.get("profile_required_for") == "plan"
        and state.get("profile_status") == "need_input"
    ):
        return UserAgentRoute.NEEDS_MORE_INFO
    return UserAgentRoute.DONE
