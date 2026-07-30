"""LLM judge for the topic-scope guardrail.

Consulted by check_topic_scope (core/agents/tools.py) for every query -- there
is no keyword pre-check, this judge is the sole decision-maker for whether a
query is in-scope (e.g. "how do I recover faster" or "help me get shredded"
are in-scope despite not having an obvious fitness keyword).

The judge classifies by ACTIONABLE REQUEST, not by whether fitness words or
context merely appear in the message. Background/motivation ("I want to
train at the beach") is not itself a request, so a message that only wraps
an out-of-scope ask in fitness-sounding context (e.g. "I want to train at
the beach, give me the weather of Danang city") is a REJECT, not MIXED --
there is exactly one actionable request (the weather lookup) and it's
unsupported. MIXED is reserved for messages with two genuinely separate,
independently-answerable asks. See _JUDGE_SYSTEM_PROMPT's worked examples.
"""

from collections.abc import Callable
from typing import Literal

from langchain_core.messages import HumanMessage, SystemMessage
from pydantic import BaseModel, Field

from core.adapters.llm.factory import invoke_standard_structured_output
from core.adapters.llm.metrics import reset_llm_metrics_node, set_llm_metrics_node
from core.adapters.llm.prompt_fragments import JSON_ONLY_INSTRUCTION

ActionType = Literal[
    # Supported (in-scope) actions.
    "training_plan",
    "exercise_recommendation",
    "macro_calculation",
    "calorie_calculation",
    "nutrition_guidance",
    "recovery_guidance",
    "injury_guidance",
    "fitness_education",
    # Unsupported (out-of-scope) actions.
    "weather_lookup",
    "news_lookup",
    "finance",
    "coding",
    "translation",
    "travel",
    "shopping",
    "entertainment",
    "legal",
    "medical",
    "general_knowledge",
    "other",
]

ScopeDecision = Literal["ALLOW", "REJECT", "MIXED", "CLARIFY"]


class ScopeRequest(BaseModel):
    """One concrete, actionable request identified in the user's message.

    Background, motivation, and context are deliberately excluded -- only text
    that asks the assistant to produce something becomes a ScopeRequest.
    """

    text: str = Field(description="The user's own words for this actionable request.")
    action_type: ActionType
    supported: bool


class TopicScopeJudgement(BaseModel):
    """LLM verdict on which actionable requests (if any) this assistant should act on.

    `decision` is ALLOW when every actionable request is supported, REJECT when
    none are, MIXED when both a supported and an unsupported request are
    present, and CLARIFY when there's no concrete actionable request yet
    (requests is then empty). See check_topic_scope for how `decision` and
    `requests` become a block/pass/partial routing outcome.
    """

    decision: ScopeDecision
    requests: list[ScopeRequest] = Field(
        description="Every actionable request identified in the message; empty for CLARIFY."
    )
    reason: str = Field(description="One concise sentence explaining the decision.")


TopicScopeJudge = Callable[[str], TopicScopeJudgement]

_JUDGE_OVERRIDE: TopicScopeJudge | None = None

_JUDGE_SYSTEM_PROMPT = (
    """You are the scope validator for a fitness planning assistant.

Your job is NOT to answer the user.

Your only job is to determine whether the assistant should continue processing
the user's request.

The assistant supports only:

- workout planning
- training program design
- exercise recommendations
- fitness goals
- strength, muscle gain, fat loss
- nutrition guidance
- calorie calculation
- macro calculation
- recovery advice
- exercise modification
- fitness education

Everything else is outside the assistant's scope.

--------------------------------------------------
Step 1 — Identify actionable requests
--------------------------------------------------

Extract every concrete request that requires the assistant to perform a task.

Ignore:

- background information
- motivation
- goals
- explanations
- context

Examples

"I want to lose weight."

→ no actionable request

"I want to lose weight. Build me a workout."

→ one actionable request

"Build me a workout and tell me tomorrow's weather."

→ two actionable requests

--------------------------------------------------
Step 2 — Classify each request
--------------------------------------------------

Assign exactly one action_type to every actionable request.

Supported action types:

- training_plan
- exercise_recommendation
- macro_calculation
- calorie_calculation
- nutrition_guidance
- recovery_guidance
- injury_guidance
- fitness_education

Unsupported action types:

- weather_lookup
- news_lookup
- finance
- coding
- translation
- travel
- shopping
- entertainment
- legal
- medical
- general_knowledge
- other

Never invent new action types.

--------------------------------------------------
Step 3 — Determine the decision
--------------------------------------------------

ALLOW
Every actionable request is supported.

REJECT
Every actionable request is unsupported.

MIXED
The message contains both supported and unsupported actionable requests.

CLARIFY
There is no actionable request because the user's intent is too incomplete or
ambiguous.

--------------------------------------------------
Rules
--------------------------------------------------

Always classify the requested ACTION, not surrounding context.

Fitness-related wording does not make a request fitness-related.

Example:

"I want to train at the beach.
Tell me tomorrow's weather."

Result:
- one request: weather_lookup
- decision: REJECT

Weather can also be context.

Example:

"It's hot outside.
Recommend a workout that won't overheat me."

Result:
- one request: exercise_recommendation
- decision: ALLOW

Do not split a single fitness objective into multiple requests.

Example:

"I want to lose weight.
How many calories should I eat?"

This is one request:
- calorie_calculation

Asking whether stated calorie or macro intake is appropriate for a fitness goal
IS an actionable request — do not CLARIFY just because the user also mentions a
goal like weight loss as context.

Example:

"I want to know if my current macros are appropriate for weight loss.
I'm currently consuming 3,000 calories per day."

This is one request:
- macro_calculation
- decision: ALLOW

Example:

"Are my macros right for cutting?"

This is one request:
- macro_calculation
- decision: ALLOW
"""
    + JSON_ONLY_INSTRUCTION
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
