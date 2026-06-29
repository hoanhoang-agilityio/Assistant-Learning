import asyncio
import json
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

from langchain_core.tools import BaseTool
from langchain_mcp_adapters.client import MultiServerMCPClient

from core.config.settings import Settings, get_settings

TAVILY_SEARCH_TOOL = "tavily-search"
TAVILY_EXTRACT_TOOL = "tavily-extract"


def _parse_tool_payload(result: Any) -> dict[str, Any]:
    if isinstance(result, dict):
        return result
    if isinstance(result, str):
        try:
            parsed = json.loads(result)
        except json.JSONDecodeError:
            return {"results": [{"content": result}]}
        if isinstance(parsed, dict):
            return parsed
        return {"results": parsed}
    return {"results": [{"content": str(result)}]}


def _invoke_tool(tool: BaseTool, payload: dict[str, Any]) -> dict[str, Any]:
    return _parse_tool_payload(tool.invoke(payload))


@dataclass(frozen=True)
class TavilyMCPClient:
    """Thin wrapper around official Tavily MCP tools."""

    search: Callable[[str], dict[str, Any]]
    extract: Callable[[list[str]], dict[str, Any]]


def build_tavily_connections(settings: Settings) -> dict[str, dict[str, Any]]:
    """Build MultiServerMCPClient connection config for official Tavily MCP."""
    if not settings.tavily_api_key:
        raise ValueError("TAVILY_API_KEY is required to connect to Tavily MCP")

    return {
        "tavily": {
            "transport": "streamable_http",
            "url": f"{settings.tavily_mcp_url}?tavilyApiKey={settings.tavily_api_key}",
        }
    }


async def create_tavily_mcp_client(settings: Settings | None = None) -> TavilyMCPClient:
    """Load Tavily MCP tools via langchain-mcp-adapters (pre-built server only)."""
    resolved_settings = settings or get_settings()
    connections = build_tavily_connections(resolved_settings)
    client = MultiServerMCPClient(connections=connections)
    tools = await client.get_tools()
    tools_by_name = {tool.name: tool for tool in tools}

    missing_tools = [
        tool_name
        for tool_name in (TAVILY_SEARCH_TOOL, TAVILY_EXTRACT_TOOL)
        if tool_name not in tools_by_name
    ]
    if missing_tools:
        available = ", ".join(sorted(tools_by_name))
        missing = ", ".join(missing_tools)
        raise RuntimeError(f"Missing Tavily MCP tools [{missing}]. Available: {available}")

    search_tool = tools_by_name[TAVILY_SEARCH_TOOL]
    extract_tool = tools_by_name[TAVILY_EXTRACT_TOOL]
    return TavilyMCPClient(
        search=lambda query: _invoke_tool(search_tool, {"query": query}),
        extract=lambda urls: _invoke_tool(extract_tool, {"urls": urls}),
    )


def create_tavily_mcp_client_sync(settings: Settings | None = None) -> TavilyMCPClient:
    """Synchronous helper for non-async call sites."""
    return asyncio.run(create_tavily_mcp_client(settings=settings))


_client: TavilyMCPClient | None = None


def configure_tavily_client(client: TavilyMCPClient | None) -> None:
    """Inject or reset the Tavily MCP client (used in tests)."""
    global _client
    _client = client


def get_tavily_client() -> TavilyMCPClient:
    """Return the configured Tavily MCP client."""
    if _client is None:
        return create_tavily_mcp_client_sync()
    return _client
