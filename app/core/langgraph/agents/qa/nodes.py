"""Nodes of the general-QA agent."""

import asyncio
import json

from langchain_core.messages import SystemMessage, ToolMessage
from langchain_core.runnables import RunnableConfig
from langgraph.graph import END
from langgraph.types import Command

from app.core.langgraph.agents.qa.state import QAState
from app.core.langgraph.tools import tools
from app.core.langgraph.utils import dump_messages, message_text
from app.core.logging import logger
from app.core.prompts import load_qa_prompt
from app.services.llm.service import llm_service

_TOOLS_BY_NAME = {tool.name: tool for tool in tools}


async def answer_qa(state: QAState, config: RunnableConfig) -> Command:
    """Answer a knowledge question, optionally after a knowledge-base lookup.

    Reads ``messages``, ``plan_context`` and ``long_term_memory``. Writes
    ``messages`` and ``answer``.

    Args:
        state: Current QA state.
        config: Runnable config. Callbacks propagate to the LLM call through
            contextvars.

    Returns:
        A command going to ``tool_call`` when the model asked for a tool, else
        to ``END`` with the answer text.
    """
    messages = [
        SystemMessage(
            content=load_qa_prompt(state["plan_context"], state.get("long_term_memory", ""))
        ),
        *state["messages"],
    ]

    try:
        response = await llm_service.call(dump_messages(messages))
    except Exception as e:
        logger.exception("qa_llm_call_failed", error=str(e))
        return Command(
            update={"answer": "I could not answer that just now. Please try again."},
            goto=END,
        )

    if getattr(response, "tool_calls", None):
        logger.info("qa_tool_requested", tool_count=len(response.tool_calls))
        return Command(update={"messages": [response]}, goto="tool_call")

    answer = message_text(response)
    logger.info("qa_answered", answer_length=len(answer))
    return Command(update={"messages": [response], "answer": answer}, goto=END)


async def tool_call(state: QAState, config: RunnableConfig) -> Command:
    """Execute the tools the model requested and hand control back.

    Reads the last message in ``messages``. Writes ``messages``.

    Args:
        state: Current QA state whose last message carries ``tool_calls``.
        config: Runnable config. Unused.

    Returns:
        A command appending one tool message per call and going to ``answer_qa``.
    """
    calls = state["messages"][-1].tool_calls
    results = await asyncio.gather(*(_run_one(call) for call in calls), return_exceptions=False)
    return Command(update={"messages": results}, goto="answer_qa")


async def _run_one(call: dict) -> ToolMessage:
    """Invoke a single tool call, turning failure into a tool message.

    A raised exception here would abort the turn; a tool message saying the
    lookup failed lets the model answer from its own knowledge and say so.

    Args:
        call: The ``tool_calls`` entry to execute.

    Returns:
        The tool result as a ``ToolMessage``.
    """
    tool = _TOOLS_BY_NAME.get(call["name"])
    if tool is None:
        logger.warning("qa_unknown_tool_requested", tool_name=call["name"])
        return ToolMessage(content=f"unknown tool: {call['name']}", tool_call_id=call["id"])

    try:
        output = await tool.ainvoke(call["args"])
        return ToolMessage(content=json.dumps(output), tool_call_id=call["id"])
    except Exception as e:
        logger.exception("qa_tool_failed", tool_name=call["name"], error=str(e))
        return ToolMessage(content=f"tool {call['name']} failed", tool_call_id=call["id"])
