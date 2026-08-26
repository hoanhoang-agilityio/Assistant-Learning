"""What the agents' tools read out of their runtime rather than from the model."""

from typing import Any

from langchain.tools import ToolRuntime
from pydantic import ValidationError

from src.schemas import CoachContext, QaContext, UserProfile

AgentContext = CoachContext | QaContext


def context_profile(runtime: ToolRuntime[AgentContext, Any]) -> UserProfile | None:
    """The user's profile as the agent was invoked with it, or None when it is unusable."""

    context = runtime.context
    if not isinstance(context, CoachContext | QaContext) or not context.profile:
        return None

    try:
        return UserProfile.model_validate(context.profile)
    except ValidationError:
        return None


def context_user_id(runtime: ToolRuntime[AgentContext, Any]) -> str:
    """The id of the user the agent was invoked for, or "" when the runtime carries none."""

    context = runtime.context
    if not isinstance(context, CoachContext | QaContext):
        return ""

    return context.user_id
