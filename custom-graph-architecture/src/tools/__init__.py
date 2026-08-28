"""Tools the agents' LLM nodes may call."""

from langchain_core.tools import BaseTool

from src.tools.profile import get_user_profile, update_user_profile

USER_AGENT_TOOLS: list[BaseTool] = [get_user_profile, update_user_profile]

__all__ = [
    "USER_AGENT_TOOLS",
    "get_user_profile",
    "update_user_profile",
]
