"""Shared MCP tool-invocation plumbing for langchain-mcp-adapters based clients
(core.adapters.mcp.tavily_client, core.adapters.mcp.fitness_client) -- asyncio bridging and MCP
content-block response parsing, extracted so it isn't duplicated per client.
"""

import asyncio
import concurrent.futures
import json
from collections.abc import Awaitable
from typing import Any

from langchain_core.tools import BaseTool


def run_async(coro: Awaitable[Any]) -> Any:
    try:
        asyncio.get_running_loop()
    except RuntimeError:
        return asyncio.run(coro)

    with concurrent.futures.ThreadPoolExecutor(max_workers=1) as executor:
        return executor.submit(asyncio.run, coro).result()


def parse_text_payload(text: str) -> dict[str, Any]:
    try:
        parsed = json.loads(text)
    except json.JSONDecodeError:
        return {"results": [{"content": text}]}
    if isinstance(parsed, dict):
        return parsed
    return {"results": parsed}


def parse_tool_payload(result: Any) -> dict[str, Any]:
    if isinstance(result, dict):
        return result
    if isinstance(result, list):
        text_parts = [
            str(block.get("text", ""))
            for block in result
            if isinstance(block, dict) and block.get("type") == "text"
        ]
        if text_parts:
            return parse_text_payload("\n".join(text_parts))
        return {"results": result}
    if isinstance(result, str):
        return parse_text_payload(result)
    return {"results": [{"content": str(result)}]}


def invoke_tool(tool: BaseTool, payload: dict[str, Any], *, timeout: float) -> dict[str, Any]:
    result = run_async(asyncio.wait_for(tool.ainvoke(payload), timeout=timeout))
    return parse_tool_payload(result)


def resolve_tool_name(
    tools_by_name: dict[str, BaseTool],
    aliases: tuple[str, ...],
) -> str | None:
    for name in aliases:
        if name in tools_by_name:
            return name
    return None
