"""Tools the agents' LLM nodes may call."""

from langchain_core.tools import BaseTool

from src.core.langgraph.tools.load_template import load_template

COACH_TOOLS: list[BaseTool] = [load_template]

__all__ = ["COACH_TOOLS", "load_template"]
