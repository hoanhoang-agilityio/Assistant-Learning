"""Compatibility re-export for the agent registry."""

from app.core.langgraph.agents import registry as _registry

AGENTS = _registry.AGENTS
_built = _registry._built
get_agent = _registry.get_agent

__all__ = ["AGENTS", "get_agent"]
