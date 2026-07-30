import asyncio
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

from langchain_core.tools import BaseTool
from langchain_mcp_adapters.client import MultiServerMCPClient

from core.config.settings import Settings, get_settings
from core.mcp._transport import invoke_tool, resolve_tool_name

TAVILY_SEARCH_TOOL = "tavily_search"
TAVILY_EXTRACT_TOOL = "tavily_extract"
TAVILY_SEARCH_TOOL_ALIASES = (TAVILY_SEARCH_TOOL, "tavily-search")
TAVILY_EXTRACT_TOOL_ALIASES = (TAVILY_EXTRACT_TOOL, "tavily-extract")


def _invoke_tool(tool: BaseTool, payload: dict[str, Any]) -> dict[str, Any]:
    """Reads the timeout fresh from settings on every call (not resolved once and
    closed over) -- this is what lets tests monkeypatch get_settings and call this
    directly without rebuilding the whole client (see tests/test_tavily_client.py)."""
    return invoke_tool(tool, payload, timeout=get_settings().tavily_tool_timeout_seconds)


@dataclass(frozen=True)
class TavilyMCPClient:
    """Thin wrapper around official Tavily MCP tools.

    `search`'s second (optional) argument is `include_domains` -- only ever
    passed a non-None value when `research_trusted_domains` is explicitly
    configured (see search_tavily_data in research/utils.py); the built-in
    default domain list is deliberately never sent to Tavily itself, since
    `include_domains` is a literal-domain hard filter with no `.edu`/`.gov`
    wildcard, and hard-restricting every search by default would cut real
    recall for a scoping tool most callers never opted into.
    """

    search: Callable[..., dict[str, Any]]
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
    tools = await asyncio.wait_for(
        client.get_tools(), timeout=resolved_settings.tavily_tool_timeout_seconds
    )
    tools_by_name = {tool.name: tool for tool in tools}

    search_tool_name = resolve_tool_name(tools_by_name, TAVILY_SEARCH_TOOL_ALIASES)
    extract_tool_name = resolve_tool_name(tools_by_name, TAVILY_EXTRACT_TOOL_ALIASES)
    missing_tools = [
        tool_name
        for tool_name, resolved in (
            (TAVILY_SEARCH_TOOL, search_tool_name),
            (TAVILY_EXTRACT_TOOL, extract_tool_name),
        )
        if resolved is None
    ]
    if missing_tools:
        available = ", ".join(sorted(tools_by_name))
        missing = ", ".join(missing_tools)
        raise RuntimeError(f"Missing Tavily MCP tools [{missing}]. Available: {available}")

    search_tool = tools_by_name[search_tool_name]
    extract_tool = tools_by_name[extract_tool_name]

    def _search(query: str, include_domains: list[str] | None = None) -> dict[str, Any]:
        payload: dict[str, Any] = {"query": query, "max_results": 5, "search_depth": "advanced"}
        if include_domains:
            payload["include_domains"] = include_domains
        return _invoke_tool(search_tool, payload)

    return TavilyMCPClient(
        search=_search,
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
