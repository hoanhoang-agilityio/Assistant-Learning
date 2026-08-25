"""The ``coach_agent`` node: a tool-using agent that writes the user's training plan."""

from functools import lru_cache
from typing import TypedDict

from langchain.agents import create_agent
from langchain_core.messages import AIMessage, AnyMessage, HumanMessage
from langchain_openai import ChatOpenAI
from langgraph.graph.state import CompiledStateGraph

from src.core.configs.config import settings
from src.core.langgraph.prompts import (
    COACH_AGENT_SYSTEM,
    as_prompt_json,
    build_coach_context,
)
from src.core.langgraph.tools import COACH_TOOLS
from src.schemas import CoachContext, GraphState, TrainingPlan
from src.utils.logging import logger

COACH_AGENT_NAME = "coach_agent"
NO_PROFILE = "none on record"
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
        context_schema=CoachContext,
        name=COACH_AGENT_NAME,
    )


def _confirmed_slots(plan: dict | None, verification: dict | None) -> list[dict] | None:
    """Prescriptions the last verification pass raised no error against.

    Warnings do not disqualify a slot: the gate lets a plan through with them standing, so
    a slot flagged only by a warning is still one the coach agent need not touch again.
    """

    if not plan or not verification:
        return None

    flagged = {
        (issue.get("day_number"), issue.get("slot_id"))
        for issue in verification.get("issues", [])
        if issue.get("severity") == "error"
    }

    confirmed = [
        {
            "day_number": day.get("day_number"),
            "slot_id": exercise.get("slot_id"),
            "exercise_id": exercise.get("exercise_id"),
        }
        for day in plan.get("training_days", [])
        for exercise in day.get("exercises", [])
        if (day.get("day_number"), exercise.get("slot_id")) not in flagged
    ]

    return confirmed or None


def build_coach_input(state: GraphState) -> list[AnyMessage]:
    """Assemble what the agent sees: the conversation so far plus this turn's context."""

    context = build_coach_context(
        user_query=state["user_query"],
        profile=as_prompt_json(state.get("profile")) or NO_PROFILE,
        plan=as_prompt_json(state.get("plan")),
        verification_errors=as_prompt_json(state.get("verification_result")),
        reviewer_feedback=state.get("hitl_feedback"),
        confirmed_slots=as_prompt_json(
            _confirmed_slots(state.get("plan"),
                             state.get("verification_result"))
        ),
    )
    return [*state["messages"], HumanMessage(content=context)]


async def coach_agent(state: GraphState) -> CoachUpdate:
    """Generate or revise the user's training plan."""

    try:
        result = await build_coach_agent().ainvoke(
            {"messages": build_coach_input(state)},
            context=CoachContext(profile=state.get("profile")),
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
