"""Tools the agents' LLM nodes may call."""

from langchain_core.tools import BaseTool

from src.core.langgraph.tools.calc_macro import calc_macro
from src.core.langgraph.tools.load_exercise import load_exercise
from src.core.langgraph.tools.load_template import load_template

COACH_TOOLS: list[BaseTool] = [load_template, load_exercise]

QA_TOOLS: list[BaseTool] = [calc_macro]

__all__ = [
    "COACH_TOOLS",
    "QA_TOOLS",
    "calc_macro",
    "load_exercise",
    "load_template",
]
