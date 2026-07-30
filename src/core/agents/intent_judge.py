"""LLM judge for Supervisor intent classification."""

from collections.abc import Callable

from langchain_core.messages import HumanMessage, SystemMessage
from pydantic import BaseModel, Field

from core.agents.execution_context import Intent
from core.llm.factory import invoke_standard_structured_output
from core.llm.metrics import reset_llm_metrics_node, set_llm_metrics_node
from core.llm.prompt_fragments import JSON_ONLY_INSTRUCTION


class UserIntentJudgement(BaseModel):
    """LLM verdict on what action the user wants performed."""

    intent: Intent
    reason: str = Field(description="One short sentence explaining the verdict.")
    mentions_submitted_plan: bool = Field(
        description=(
            "True if the user pasted or clearly referenced an existing plan they want "
            "checked rather than asking for a new one."
        )
    )
    touches_goal_or_constraints: bool = Field(
        description=(
            "Only meaningful for edit_plan. True when the change affects goal, "
            "constraints, or training frequency rather than only workout content."
        )
    )


UserIntentJudge = Callable[[str], UserIntentJudgement]

_JUDGE_OVERRIDE: UserIntentJudge | None = None

_JUDGE_SYSTEM_PROMPT = (
    """You are the intent classifier for a fitness planning assistant.

Classify the user's message into exactly one intent:

- build_plan: create a new workout program, training schedule, or macro targets.
- edit_plan: change an existing plan from this assistant (swap exercise, add day, etc.).
- verify_plan: review a user-provided or external plan without regenerating it.
- verify_macros: check whether macro targets are appropriate for the user's goal.
- research_question: ask for evidence, guidelines, or research-backed fitness information.
- fitness_question: general fitness Q&A not requiring a new plan or external research.
- calculate_calories: calculate calories, TDEE, or macro targets without building a plan.

Examples:
"Build me a 4-day upper/lower split." -> build_plan
"Swap bench press for dumbbell press." -> edit_plan (touches_goal_or_constraints: false)
"Switch my goal from fat loss to strength." -> edit_plan (touches_goal_or_constraints: true)
"Here's my plan: [text]. Is it balanced?" -> verify_plan (mentions_submitted_plan: true)
"Are my macros right for cutting?" -> verify_macros
"I want to know if my current macros are appropriate for weight loss. I'm currently consuming 3,000 calories per day." -> verify_macros
"What does research say about HIIT for fat loss?" -> research_question
"How many rest days should I take?" -> fitness_question
"Calculate my TDEE and macros." -> calculate_calories"""
    + JSON_ONLY_INSTRUCTION
    + "\n"
)


def configure_user_intent_judge(judge: UserIntentJudge | None) -> None:
    global _JUDGE_OVERRIDE
    _JUDGE_OVERRIDE = judge


def judge_user_intent(query: str) -> UserIntentJudgement:
    if _JUDGE_OVERRIDE is not None:
        return _JUDGE_OVERRIDE(query)
    token = set_llm_metrics_node("intent_judge")
    try:
        return invoke_standard_structured_output(
            UserIntentJudgement,
            [
                SystemMessage(content=_JUDGE_SYSTEM_PROMPT),
                HumanMessage(content=query),
            ],
            prompt_cache_key="intent_judge",
        )
    finally:
        reset_llm_metrics_node(token)
