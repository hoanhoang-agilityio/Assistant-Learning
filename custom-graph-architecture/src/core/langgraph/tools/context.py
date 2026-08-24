"""What the agents' tools read out of their runtime rather than from the model."""

from typing import Any

from langchain.tools import ToolRuntime
from pydantic import ValidationError

from src.schemas import CoachContext, UserProfile


def context_profile(runtime: ToolRuntime[CoachContext, Any]) -> UserProfile | None:
    """The user's profile as the agent was invoked with it, or None when it is unusable."""

    context = runtime.context
    if not isinstance(context, CoachContext) or not context.profile:
        return None

    try:
        return UserProfile.model_validate(context.profile)
    except ValidationError:
        return None
