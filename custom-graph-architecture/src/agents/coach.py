"""The ``coach_agent`` node: a tool-using agent that reads, writes and revises the user's training plan."""

from functools import lru_cache
from typing import NotRequired, TypedDict

from langchain.agents import create_agent
from langchain.agents.structured_output import ToolStrategy
from langchain_core.messages import AIMessage, AnyMessage, HumanMessage
from langgraph.graph.state import CompiledStateGraph
from pydantic import ValidationError

from src.agents.history import trim_history
from src.configs.config import settings
from src.enums import CoachRoute
from src.prompts import COACH_AGENT_SYSTEM, build_coach_context
from src.prompts.coach_agent import NO_SLOTS_TO_FIX, REVIEWER_SLOTS_TO_FIX
from src.prompts.rendering import as_prompt_json
from src.schemas import (
    CoachContext,
    CoachOutcome,
    GraphState,
    PlanAnswer,
    ProfileRequiredFor,
    ProfileStatus,
    TrainingPlan,
    UserProfile,
)
from src.services.llm import agent_middleware, chat_model
from src.services.nutrition import calc_macros
from src.services.profile import missing_profile_fields
from src.tools import COACH_TOOLS

COACH_AGENT_NAME = "coach_agent"
NO_PROFILE = "none on record"


class CoachUpdate(TypedDict):
    """The state ``coach_agent`` writes."""

    plan: NotRequired[dict | None]
    coach_outcome: CoachOutcome | None
    profile_required_for: NotRequired[ProfileRequiredFor | None]
    profile_status: NotRequired[ProfileStatus | None]
    messages: list[AnyMessage]


@lru_cache
def build_coach_agent() -> CompiledStateGraph:
    """Build the coach agent once, with its tools and both shapes of answer bound."""

    return create_agent(
        model=chat_model(max_tokens=settings.COACH_MAX_TOKENS),
        tools=COACH_TOOLS,
        middleware=agent_middleware(),
        system_prompt=COACH_AGENT_SYSTEM,
        response_format=ToolStrategy(TrainingPlan | PlanAnswer),
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


def _slots_to_fix_block(verification: dict | None, feedback: str | None) -> str | None:
    """What the retry has to look up again, or None when this is a first attempt."""

    if verification:
        return as_prompt_json(_slots_to_fix(verification)) or NO_SLOTS_TO_FIX
    if feedback:
        return REVIEWER_SLOTS_TO_FIX
    return None


def _failing_day_numbers(state: GraphState) -> set[int]:
    """The training days a fresh error was raised against on this attempt, or none."""

    verification = state.get("verification_result")
    if not verification:
        return set()

    return {
        issue["day_number"]
        for issue in verification.get("issues", [])
        if issue.get("severity") == "error" and issue.get("day_number") is not None
    }


def _narrowed_plan(plan: dict | None, failing_days: set[int]) -> dict | None:
    """The plan as shown to the agent: every day, or only the ones a retry has to fix."""

    if not plan or not failing_days:
        return plan

    return {
        **plan,
        "training_days": [
            day for day in plan["training_days"] if day["day_number"] in failing_days
        ],
    }


def _merge_revised_days(plan: dict, revised: dict, failing_days: set[int]) -> dict:
    """The plan to store: the agent's revision for the days it was asked to fix, every other day and every top-level field exactly as it was."""

    revised_days = {day["day_number"]: day for day in revised["training_days"]}
    return {
        **plan,
        "training_days": [
            revised_days[day["day_number"]]
            if day["day_number"] in failing_days and day["day_number"] in revised_days
            else day
            for day in plan["training_days"]
        ],
    }


def build_coach_input(state: GraphState) -> list[AnyMessage]:
    """Assemble what the agent sees: the conversation so far plus this turn's context."""

    verification = state.get("verification_result")
    feedback = state.get("approval_feedback")
    context = build_coach_context(
        profile=as_prompt_json(state.get("profile")) or NO_PROFILE,
        nutrition_targets=as_prompt_json(
            _nutrition_targets(state.get("profile"))),
        plan=as_prompt_json(
            _narrowed_plan(state.get("plan"), _failing_day_numbers(state))
        ),
        verification_errors=as_prompt_json(verification),
        reviewer_feedback=feedback,
        slots_to_fix=_slots_to_fix_block(verification, feedback),
    )
    return [*trim_history(state["messages"]), HumanMessage(content=context)]


async def coach_agent(state: GraphState) -> CoachUpdate:
    """Answer from the plan on record, or generate or revise the user's training plan."""

    if missing_profile_fields(state.get("profile")):
        return {
            "plan": None,
            "coach_outcome": None,
            "profile_required_for": "plan",
            "profile_status": "need_input",
            "messages": [],
        }

    try:
        result = await build_coach_agent().ainvoke(
            {"messages": build_coach_input(state)},
            context=CoachContext(
                user_id=state["user_id"], profile=state.get("profile")
            ),
        )
    except Exception:
        return {"plan": None, "coach_outcome": "drafted", "messages": []}

    response = result.get("structured_response")

    # An answer leaves ``plan`` alone: the draft this conversation was holding, if any, is
    # not something a question about the stored plan revises or discards.
    if isinstance(response, PlanAnswer) and response.answer.strip():
        return {
            "coach_outcome": "answered",
            "messages": [AIMessage(content=response.answer)],
        }

    if not isinstance(response, TrainingPlan):
        return {"plan": None, "coach_outcome": "drafted", "messages": []}

    revised = response.model_dump()
    previous = state.get("plan")
    failing_days = _failing_day_numbers(state)

    if previous and failing_days:
        revised = _merge_revised_days(previous, revised, failing_days)

    return {"plan": revised, "coach_outcome": "drafted", "messages": []}


def route_after_coach(state: GraphState) -> CoachRoute:
    """Send a plan attempt on to verification, an answer straight back, or bounce to the supervisor for the profile it cannot plan without."""

    if missing_profile_fields(state.get("profile")):
        return CoachRoute.NEEDS_PROFILE
    if state.get("coach_outcome") == "answered":
        return CoachRoute.ANSWERED
    return CoachRoute.READY
