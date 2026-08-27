"""The ``coach_agent`` node: a tool-using agent that writes the user's training plan."""

from functools import lru_cache
from typing import TypedDict

from langchain.agents import create_agent
from langchain_core.messages import AnyMessage, HumanMessage
from langgraph.graph.state import CompiledStateGraph
from pydantic import ValidationError

from src.core.configs.config import settings
from src.core.langgraph.agents.history import trim_history
from src.core.langgraph.prompts import (
    COACH_AGENT_SYSTEM,
    as_prompt_json,
    build_coach_context,
)
from src.core.langgraph.prompts.coach_agent import NO_SLOTS_TO_FIX
from src.core.langgraph.tools import COACH_TOOLS
from src.core.llm import agent_middleware, chat_model
from src.schemas import CoachContext, GraphState, TrainingPlan, UserProfile
from src.services.nutrition import calc_macros
from src.utils.logging import logger

COACH_AGENT_NAME = "coach_agent"
NO_PROFILE = "none on record"


class CoachUpdate(TypedDict):
    """The state ``coach_agent`` writes."""

    plan: dict | None


@lru_cache
def build_coach_agent() -> CompiledStateGraph:
    """Build the coach agent once, with its tools and its plan schema bound."""

    return create_agent(
        model=chat_model(max_tokens=settings.COACH_MAX_TOKENS),
        tools=COACH_TOOLS,
        middleware=agent_middleware(),
        system_prompt=COACH_AGENT_SYSTEM,
        response_format=TrainingPlan,
        context_schema=CoachContext,
        name=COACH_AGENT_NAME,
    )


def _nutrition_targets(profile: dict | None) -> dict | None:
    """The calorie and macro targets the profile works out to, computed rather than asked for."""

    if not profile:
        return None

    try:
        return calc_macros(UserProfile.model_validate(profile)).model_dump(mode="json")
    except ValidationError:
        return None


def _slots_to_fix(verification: dict) -> list[dict]:
    """The slots the last verification pass raised an error against."""

    flagged = dict.fromkeys(
        (issue.get("day_number"), issue.get("slot_id"))
        for issue in verification.get("issues", [])
        if issue.get("severity") == "error" and issue.get("slot_id")
    )

    return [
        {"day_number": day_number, "slot_id": slot_id}
        for day_number, slot_id in flagged
    ]


def _slots_to_fix_block(verification: dict | None) -> str | None:
    """What the retry has to look up again, or None when this is not a verification retry."""

    if not verification:
        return None

    return as_prompt_json(_slots_to_fix(verification)) or NO_SLOTS_TO_FIX


def build_coach_input(state: GraphState) -> list[AnyMessage]:
    """Assemble what the agent sees: the conversation so far plus this turn's context."""

    context = build_coach_context(
        user_query=state["user_query"],
        profile=as_prompt_json(state.get("profile")) or NO_PROFILE,
        nutrition_targets=as_prompt_json(_nutrition_targets(state.get("profile"))),
        plan=as_prompt_json(state.get("plan")),
        verification_errors=as_prompt_json(state.get("verification_result")),
        reviewer_feedback=state.get("hitl_feedback"),
        slots_to_fix=_slots_to_fix_block(state.get("verification_result")),
    )
    return [*trim_history(state["messages"]), HumanMessage(content=context)]


async def coach_agent(state: GraphState) -> CoachUpdate:
    """Generate or revise the user's training plan."""

    try:
        result = await build_coach_agent().ainvoke(
            {"messages": build_coach_input(state)},
            context=CoachContext(
                user_id=state["user_id"], profile=state.get("profile")
            ),
        )
    except Exception as error:
        logger.exception(
            "coach_agent_failed", user_id=state["user_id"], error=str(error)
        )
        return {"plan": None}

    plan = result.get("structured_response")
    if not isinstance(plan, TrainingPlan):
        return {"plan": None}

    return {"plan": plan.model_dump()}
