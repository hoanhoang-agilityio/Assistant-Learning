"""Deterministic default overrides for the topic-scope and request-type judges.

Production code always calls the real LLM judges (core/agents/topic_scope_judge.py,
core/agents/request_type_judge.py). Tests install these keyword-based stand-ins by
default (see conftest.py) so the supervisor graph can be exercised offline; tests that
care about a specific verdict configure their own override instead.
"""

from core.agents.request_type_judge import RequestTypeJudgement
from core.agents.state import RequestType
from core.agents.topic_scope_judge import TopicScopeJudgement

_FITNESS_TOPIC_KEYWORDS: tuple[str, ...] = (
    "workout",
    "exercise",
    "training",
    "train ",
    "gym",
    "fitness",
    "muscle",
    "strength",
    "cardio",
    "endurance",
    "hypertrophy",
    "powerlifting",
    "1rm",
    "rep ",
    "reps",
    "set ",
    "sets",
    "routine",
    "regimen",
    "diet",
    "nutrition",
    "macro",
    "calorie",
    "protein",
    "carb",
    "fat loss",
    "lose fat",
    "weight loss",
    "lose weight",
    "bulk",
    "cutting",
    "cut ",
    "recovery",
    "stretch",
    "mobility",
    "flexibility",
    "yoga",
    "running",
    "marathon",
    "jog",
    "lift",
    "lifting",
    "squat",
    "deadlift",
    "bench press",
    "supplement",
    "injury",
    "warm up",
    "warmup",
    "cool down",
    "hydration",
    "bodyweight",
    "hiit",
    "crossfit",
    "pilates",
    "sore",
    "soreness",
    "physique",
)

_REQUEST_TYPE_KEYWORDS: tuple[tuple[RequestType, tuple[str, ...]], ...] = (
    ("fat_loss", ("lose weight", "fat loss", "lose fat", "cutting", "cut ")),
    ("muscle_gain", ("muscle gain", "bulk", "hypertrophy", "build muscle")),
    ("macro_calculation", ("macro", "calories", "protein", "macros")),
    ("strength", ("strength", "powerlifting", "1rm")),
    ("endurance", ("endurance", "marathon", "cardio")),
    ("training_plan", ("training plan", "workout plan", "program")),
)


def default_topic_scope_judge(query: str) -> TopicScopeJudgement:
    """Keyword-based stand-in for the real topic-scope LLM judge."""
    query_lower = query.lower()
    is_fitness_related = any(keyword in query_lower for keyword in _FITNESS_TOPIC_KEYWORDS)
    return TopicScopeJudgement(
        is_fitness_related=is_fitness_related,
        reason="Keyword-based test stub verdict.",
    )


def default_request_type_judge(query: str) -> RequestTypeJudgement:
    """Keyword-based stand-in for the real request-type LLM judge."""
    query_lower = query.lower()
    request_type: RequestType = "general_fitness"
    for candidate_type, keywords in _REQUEST_TYPE_KEYWORDS:
        if any(keyword in query_lower for keyword in keywords):
            request_type = candidate_type
            break
    return RequestTypeJudgement(
        request_type=request_type,
        reason="Keyword-based test stub verdict.",
    )
