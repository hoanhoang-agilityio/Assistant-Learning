"""The ``qa_agent`` node: a tool-using agent that answers knowledge questions."""

from functools import lru_cache
from typing import TypedDict

from langchain.agents import create_agent
from langchain_core.messages import AIMessage, AnyMessage, HumanMessage
from langchain_openai import ChatOpenAI
from langgraph.graph.state import CompiledStateGraph

from src.core.configs.config import settings
from src.core.langgraph.prompts import QA_AGENT_SYSTEM, as_prompt_json, build_qa_context
from src.core.langgraph.tools import QA_TOOLS
from src.schemas import GraphState, QaContext
from src.services.profile import load_profile
from src.utils.logging import logger

QA_AGENT_NAME = "qa_agent"
NO_PROFILE = "none on record"


class QaUpdate(TypedDict):
    """The state ``qa_agent`` writes."""

    profile: dict | None
    qa_answer: str | None
    messages: list[AnyMessage]


@lru_cache
def build_qa_agent() -> CompiledStateGraph:
    """Build the QA agent once, with its knowledge tools bound."""

    model = ChatOpenAI(
        api_key=settings.OPENAI_API_KEY,
        model=settings.DEFAULT_LLM_MODEL,
        max_completion_tokens=settings.QA_MAX_TOKENS,
    )

    return create_agent(
        model=model,
        tools=QA_TOOLS,
        system_prompt=QA_AGENT_SYSTEM,
        context_schema=QaContext,
        name=QA_AGENT_NAME,
    )


async def qa_profile(state: GraphState) -> dict | None:
    """The user's stored profile, read here rather than gated behind a tool call."""

    profile = state.get("profile")
    if profile is not None:
        return profile

    try:
        return await load_profile(state["user_id"])
    except Exception as error:
        logger.exception(
            "qa_profile_load_failed", user_id=state["user_id"], error=str(error)
        )
        return None


def build_qa_input(state: GraphState) -> list[AnyMessage]:
    """Assemble what the agent sees: the conversation so far plus this turn's context."""

    context = build_qa_context(
        user_query=state["user_query"],
        profile=as_prompt_json(state.get("profile")) or NO_PROFILE,
        previous_answer=state.get("qa_answer"),
        faithfulness_score=state.get("ragas_score"),
    )
    return [*state["messages"], HumanMessage(content=context)]


def answer_text(messages: list[AnyMessage]) -> str | None:
    """The agent's own last word, which is the answer the faithfulness gate scores."""

    for message in reversed(messages):
        if isinstance(message, AIMessage) and isinstance(message.content, str):
            answer = message.content.strip()
            if answer:
                return answer

    return None


async def qa_agent(state: GraphState) -> QaUpdate:
    """Answer the user's knowledge question from the knowledge base."""

    profile = await qa_profile(state)

    try:
        result = await build_qa_agent().ainvoke(
            {"messages": build_qa_input(state | {"profile": profile})},
            context=QaContext(user_id=state["user_id"], profile=profile),
        )
    except Exception as error:
        logger.exception("qa_agent_failed", user_id=state["user_id"], error=str(error))
        return {"profile": profile, "qa_answer": None, "messages": []}

    answer = answer_text(result.get("messages", []))
    if answer is None:
        return {"profile": profile, "qa_answer": None, "messages": []}

    return {
        "profile": profile,
        "qa_answer": answer,
        "messages": [AIMessage(content=answer)],
    }
