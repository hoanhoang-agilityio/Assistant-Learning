"""LLM classifier for the supervisor's request_type routing decision.

Consulted by classify_request (core/agents/tools.py) for every query that
reaches classification -- there is no keyword pre-check, this judge is the
sole source of request_type.
"""

from collections.abc import Callable

from langchain_core.messages import HumanMessage, SystemMessage
from pydantic import BaseModel, Field

from core.agents.state import RequestType
from core.llm.factory import invoke_standard_structured_output
from core.llm.metrics import reset_llm_metrics_node, set_llm_metrics_node
from core.llm.prompt_fragments import JSON_ONLY_INSTRUCTION


class RequestTypeJudgement(BaseModel):
    """LLM verdict on which request_type a fitness query belongs to."""

    request_type: RequestType
    reason: str = Field(description="One short sentence explaining the verdict.")


RequestTypeJudge = Callable[[str], RequestTypeJudgement]

_JUDGE_OVERRIDE: RequestTypeJudge | None = None

_JUDGE_SYSTEM_PROMPT = (
    """You are a request-type classifier for a fitness planning assistant.

Classify the user's message into exactly one of these request_type values:
- training_plan: asking for a workout program, routine, or training schedule
- macro_calculation: asking about macros, calories, protein/carb/fat targets, or diet math
- fat_loss: primary goal is losing weight/body fat, cutting, or shredding
- muscle_gain: primary goal is building muscle, bulking, or hypertrophy
- strength: primary goal is getting stronger, powerlifting, or raising a 1RM
- endurance: primary goal is cardio endurance, running, or race distance
- general_fitness: any other fitness/nutrition/training question that doesn't fit above

Pick the single best match. If a message mentions more than one, prefer the
user's stated primary goal over incidental details (e.g. a training plan
requested in order to lose weight is fat_loss, not training_plan, if losing
weight is the stated goal).

"""
    + JSON_ONLY_INSTRUCTION
    + "\n"
)


def configure_request_type_judge(judge: RequestTypeJudge | None) -> None:
    """Override the request-type judge (used in tests)."""
    global _JUDGE_OVERRIDE
    _JUDGE_OVERRIDE = judge


def judge_request_type(query: str) -> RequestTypeJudgement:
    """Ask the LLM which request_type a query belongs to. Raises on LLM/API failure."""
    if _JUDGE_OVERRIDE is not None:
        return _JUDGE_OVERRIDE(query)
    token = set_llm_metrics_node("request_type_judge")
    try:
        return invoke_standard_structured_output(
            RequestTypeJudgement,
            [
                SystemMessage(content=_JUDGE_SYSTEM_PROMPT),
                HumanMessage(content=query),
            ],
            prompt_cache_key="request_type_judge",
        )
    finally:
        reset_llm_metrics_node(token)
