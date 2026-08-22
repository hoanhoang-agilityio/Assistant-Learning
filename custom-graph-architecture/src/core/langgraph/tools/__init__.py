"""Tools the agents' LLM nodes may call."""

from langchain_core.tools import BaseTool

COACH_TOOLS: list[BaseTool] = []

__all__ = ["COACH_TOOLS"]
