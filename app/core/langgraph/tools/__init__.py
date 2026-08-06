"""Tools shared by more than one agent.

Tools an agent alone uses live in that agent's package. A tool exists only where
the LLM has a real choice to make; mandatory steps are graph edges and
deterministic helpers are plain functions the node calls.
"""

from langchain_core.tools.base import BaseTool

from app.core.langgraph.tools.search_knowledge import search_knowledge

tools: list[BaseTool] = [search_knowledge]

__all__ = ["search_knowledge", "tools"]
