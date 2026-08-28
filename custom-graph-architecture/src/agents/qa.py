"""The ``qa_agent`` node: a tool-using agent that answers knowledge questions."""

from functools import lru_cache
from typing import TypedDict

from langchain.agents import create_agent
from langchain_core.messages import AIMessage, AnyMessage, HumanMessage, ToolMessage
from langgraph.graph.state import CompiledStateGraph

from src.agents.history import trim_history
from src.configs.config import settings
from src.prompts import QA_AGENT_SYSTEM, build_qa_context
from src.prompts.rendering import as_prompt_json
from src.schemas import GraphState, QaContext, RetrievedChunk
from src.services.llm import agent_middleware, chat_model
from src.tools import QA_TOOLS, search_knowledge

QA_AGENT_NAME = "qa_agent"
NO_PROFILE = "none on record"


class QaUpdate(TypedDict):
    """The state ``qa_agent`` writes."""

    qa_answer: str | None
    retrieved_context: list[RetrievedChunk]


@lru_cache
def build_qa_agent() -> CompiledStateGraph:
    """Build the QA agent once, with its knowledge tools bound."""

    return create_agent(
        model=chat_model(max_tokens=settings.QA_MAX_TOKENS),
        tools=QA_TOOLS,
        middleware=agent_middleware(),
        system_prompt=QA_AGENT_SYSTEM,
        context_schema=QaContext,
        name=QA_AGENT_NAME,
    )


def build_qa_input(state: GraphState) -> list[AnyMessage]:
    """Assemble what the agent sees: the conversation so far plus this turn's context."""

    context = build_qa_context(
        profile=as_prompt_json(state.get("profile")) or NO_PROFILE,
        previous_answer=state.get("qa_answer"),
        faithfulness_score=state.get("faithfulness_score"),
    )
    return [*trim_history(state["messages"]), HumanMessage(content=context)]


def answer_text(messages: list[AnyMessage]) -> str | None:
    """The agent's own last word, which is the answer the faithfulness gate scores."""

    for message in reversed(messages):
        if isinstance(message, AIMessage) and isinstance(message.content, str):
            answer = message.content.strip()
            if answer:
                return answer

    return None


def retrieved_passages(messages: list[AnyMessage]) -> list[RetrievedChunk]:
    """What the agent retrieved this turn, which is what the faithfulness gate scores it against."""

    passages: list[RetrievedChunk] = []
    seen: set[str] = set()

    for message in messages:
        if (
            not isinstance(message, ToolMessage)
            or message.name != search_knowledge.name
        ):
            continue

        for passage in message.artifact or []:
            if passage["text"] not in seen:
                seen.add(passage["text"])
                passages.append(passage)

    return passages


async def qa_agent(state: GraphState) -> QaUpdate:
    """Answer the user's knowledge question from the knowledge base."""

    try:
        result = await build_qa_agent().ainvoke(
            {"messages": build_qa_input(state)},
            context=QaContext(user_id=state["user_id"], profile=state.get("profile")),
        )
    except Exception:
        return {"qa_answer": None, "retrieved_context": []}

    messages = result.get("messages", [])
    passages = retrieved_passages(messages)
    answer = answer_text(messages)

    return {"qa_answer": answer, "retrieved_context": passages}
