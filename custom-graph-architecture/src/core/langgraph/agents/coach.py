"""The ``coach_agent`` node: a tool-using agent that writes the user's training plan."""

import json
from functools import lru_cache
from typing import Any, TypedDict

from langchain.agents import create_agent
from langchain_core.messages import AIMessage, AnyMessage, HumanMessage
from langchain_openai import ChatOpenAI
from langgraph.graph.state import CompiledStateGraph

from src.core.configs.config import settings
from src.core.langgraph.prompts import COACH_AGENT_SYSTEM, build_coach_context
from src.core.langgraph.tools import COACH_TOOLS
from src.schemas import GraphState, TrainingPlan
from src.utils.logging import logger

COACH_AGENT_NAME = "coach_agent"
NO_PROFILE = "none on record"
NO_TODO = "no todo list was written; work from the user's request"
PLAN_READY_MESSAGE = "I've put your training plan together."


class CoachUpdate(TypedDict):
    """The state ``coach_agent`` writes."""

    plan: dict | None
    messages: list[AnyMessage]


@lru_cache
def build_coach_agent() -> CompiledStateGraph:
    """Build the coach agent once, with its tools and its plan schema bound."""

    model = ChatOpenAI(
        api_key=settings.OPENAI_API_KEY,
        model=settings.DEFAULT_LLM_MODEL,
        max_completion_tokens=settings.COACH_MAX_TOKENS,
    )

    return create_agent(
        model=model,
        tools=COACH_TOOLS,
        system_prompt=COACH_AGENT_SYSTEM,
        response_format=TrainingPlan,
        name=COACH_AGENT_NAME,
    )


def _as_prompt_json(value: Any) -> str | None:
    """Render a profile, plan or todo list for the prompt, or None when it is empty."""

    if not value:
        return None
    return json.dumps(value, indent=2, sort_keys=True, default=str)


def build_coach_input(state: GraphState) -> list[AnyMessage]:
    """Assemble what the agent sees: the conversation so far plus this turn's context."""

    context = build_coach_context(
        user_query=state["user_query"],
        profile=_as_prompt_json(state.get("profile")) or NO_PROFILE,
        plan=_as_prompt_json(state.get("plan")),
        todo=_as_prompt_json(state.get("todo")) or NO_TODO,
        verification_errors=_as_prompt_json(state.get("verification_result")),
        reviewer_feedback=state.get("hitl_feedback"),
    )
    return [*state["messages"], HumanMessage(content=context)]


async def coach_agent(state: GraphState) -> CoachUpdate:
    """Generate or revise the user's training plan."""

    try:
        result = await build_coach_agent().ainvoke(
            {"messages": build_coach_input(state)}
        )
    except Exception as error:
        logger.exception(
            "coach_agent_failed", user_id=state["user_id"], error=str(error)
        )
        return {"plan": None, "messages": []}

    plan = result.get("structured_response")
    if not isinstance(plan, TrainingPlan):
        return {"plan": None, "messages": []}

    return {
        "plan": plan.model_dump(),
        "messages": [AIMessage(content=plan.summary or PLAN_READY_MESSAGE)],
    }
