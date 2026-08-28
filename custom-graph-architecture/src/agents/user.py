"""The ``user_agent`` node: a tool-using agent that reads and writes the user's profile."""

from functools import lru_cache
from typing import TypedDict

from langchain.agents import create_agent
from langchain_core.messages import AIMessage, AnyMessage, ToolMessage
from langgraph.graph.state import CompiledStateGraph

from src.core.llm import agent_middleware, chat_model
from src.enums import UserAgentRoute
from src.prompts import USER_AGENT_SYSTEM
from src.schemas import GraphState, PendingApproval, UserAgentContext
from src.tools import USER_AGENT_TOOLS, get_user_profile, update_user_profile

USER_AGENT_NAME = "user_agent"


class UserAgentUpdate(TypedDict):
    """The state ``user_agent`` writes."""

    profile: dict | None
    pending_approval: PendingApproval | None
    messages: list[AnyMessage]


@lru_cache
def build_user_agent() -> CompiledStateGraph:
    """Build the user agent once, with its profile tools bound."""

    return create_agent(
        model=chat_model(),
        tools=USER_AGENT_TOOLS,
        middleware=agent_middleware(),
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


def _pending_approval(
    messages: list[AnyMessage], summary: str | None
) -> PendingApproval | None:
    """The overwrite ``update_user_profile`` staged this turn, if any."""

    artifact = _tool_artifact(messages, update_user_profile.name)
    if not artifact or artifact.get("status") != "pending_approval":
        return None

    return PendingApproval(
        source="user_agent",
        kind="profile_update",
        summary=summary or f"Update {artifact['field']} to {artifact['value']!r}?",
        payload={artifact["field"]: artifact["value"]},
    )


def _updated_profile(messages: list[AnyMessage]) -> dict | None:
    """The profile ``update_user_profile``'s direct write, or ``get_user_profile``'s read, left current."""

    for name in (update_user_profile.name, get_user_profile.name):
        artifact = _tool_artifact(messages, name)
        if artifact and isinstance(artifact.get("profile"), dict):
            return artifact["profile"]

    return None


async def user_agent(state: GraphState) -> UserAgentUpdate:
    """Read or write the user's profile, staging an overwrite for approval when one is needed."""

    try:
        result = await build_user_agent().ainvoke(
            {"messages": state["messages"]},
            context=UserAgentContext(user_id=state["user_id"]),
        )
    except Exception:
        return {
            "profile": state.get("profile"),
            "pending_approval": None,
            "messages": [],
        }

    messages = result.get("messages", [])
    reply = _final_reply(messages)

    return {
        "profile": _updated_profile(messages) or state.get("profile"),
        "pending_approval": _pending_approval(messages, reply),
        "messages": [AIMessage(content=reply)] if reply else [],
    }


def route_after_user_agent(state: GraphState) -> UserAgentRoute:
    """Send a staged overwrite to approval, or straight back to the supervisor."""

    if state.get("pending_approval") is not None:
        return UserAgentRoute.PENDING_APPROVAL
    return UserAgentRoute.DONE
