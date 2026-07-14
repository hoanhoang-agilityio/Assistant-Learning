"""LLM judge for the topic-scope guardrail.

Consulted by check_topic_scope (core/agents/tools.py) for every query -- there
is no keyword pre-check, this judge is the sole decision-maker for whether a
query is in-scope (e.g. "how do I recover faster" or "help me get shredded"
are in-scope despite not having an obvious fitness keyword).
"""

from collections.abc import Callable

from langchain_core.messages import HumanMessage, SystemMessage
from pydantic import BaseModel, Field

from core.llm.factory import invoke_standard_structured_output
from core.llm.metrics import reset_llm_metrics_node, set_llm_metrics_node
from core.llm.prompt_fragments import JSON_ONLY_INSTRUCTION


class TopicScopeJudgement(BaseModel):
    """LLM verdict on whether a query is in the fitness/nutrition/training domain."""

    is_fitness_related: bool
    reason: str = Field(description="One short sentence explaining the verdict.")


TopicScopeJudge = Callable[[str], TopicScopeJudgement]

_JUDGE_OVERRIDE: TopicScopeJudge | None = None

_JUDGE_SYSTEM_PROMPT = (
    """You are a scope classifier for a fitness planning assistant.

Decide whether the user's message is about fitness, exercise, training,
nutrition/diet, macros, recovery, or a related health/body goal -- including
phrasing that doesn't use an obvious fitness keyword (e.g. "help me get
shredded", "I want to feel stronger doing yard work", "how do I stop being
sore all the time").

Return is_fitness_related=true only if the message is plausibly asking for
help within that domain. Return false for anything else (general knowledge,
coding, entertainment, unrelated advice, etc.), even if it mentions a body
part or the word "health" in an unrelated context.

"""
    + JSON_ONLY_INSTRUCTION
    + "\n"
)


def configure_topic_scope_judge(judge: TopicScopeJudge | None) -> None:
    """Override the topic-scope judge (used in tests)."""
    global _JUDGE_OVERRIDE
    _JUDGE_OVERRIDE = judge


def judge_topic_scope(query: str) -> TopicScopeJudgement:
    """Ask the LLM whether a query is fitness-related. Raises on LLM/API failure."""
    if _JUDGE_OVERRIDE is not None:
        return _JUDGE_OVERRIDE(query)
    token = set_llm_metrics_node("topic_scope_judge")
    try:
        return invoke_standard_structured_output(
            TopicScopeJudgement,
            [
                SystemMessage(content=_JUDGE_SYSTEM_PROMPT),
                HumanMessage(content=query),
            ],
            prompt_cache_key="topic_scope_judge",
        )
    finally:
        reset_llm_metrics_node(token)
