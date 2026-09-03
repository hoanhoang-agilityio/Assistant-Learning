"""Tools the agents' LLM nodes may call."""

from langchain_core.tools import BaseTool

from src.tools.calc_macro import calc_macro
from src.tools.load_exercise import load_exercise
from src.tools.load_template import load_template
from src.tools.plan import get_plan
from src.tools.profile import get_user_profile, update_user_profile
from src.tools.search_knowledge import search_knowledge

COACH_TOOLS: list[BaseTool] = [get_plan, load_template, load_exercise]

QA_TOOLS: list[BaseTool] = [search_knowledge, calc_macro]

USER_AGENT_TOOLS: list[BaseTool] = [get_user_profile, update_user_profile]

__all__ = [
    "COACH_TOOLS",
    "QA_TOOLS",
    "USER_AGENT_TOOLS",
    "calc_macro",
    "get_plan",
    "get_user_profile",
    "load_exercise",
    "load_template",
    "search_knowledge",
    "update_user_profile",
]
