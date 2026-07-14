"""LangChain tools bound to the Research Agent's ReAct loop."""

import json

from langchain_core.tools import BaseTool, tool

from core.subgraphs.research.utils import extract_tavily_data, search_tavily_data


@tool
def tavily_search(query: str) -> str:
    """Search external fitness evidence via Tavily MCP for a single optimized query."""
    result = search_tavily_data(query)
    return json.dumps(
        {
            "query": result["query"],
            "source_count": len(result["sources"]),
            "sources": result["sources"][:5],
        }
    )


@tool
def tavily_extract(urls: list[str]) -> str:
    """Extract full document content from URLs via Tavily MCP."""
    result = extract_tavily_data(urls)
    return json.dumps(
        {
            "document_count": len(result["evidence"]),
            "evidence": [
                {
                    "url": item.get("url"),
                    "content_preview": str(item.get("content", ""))[:500],
                }
                for item in result["evidence"]
            ],
        }
    )


RESEARCH_AGENT_TOOLS: list[BaseTool] = [tavily_search, tavily_extract]
