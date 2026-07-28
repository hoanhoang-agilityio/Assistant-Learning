"""Deterministic default overrides for topic-scope and intent judges."""

from core.agents.intent_judge import UserIntentJudgement
from core.agents.topic_scope_judge import ScopeRequest, TopicScopeJudgement

_FITNESS_TOPIC_KEYWORDS: tuple[str, ...] = (
    "workout",
    "exercise",
    "training",
    "train ",
    "gym",
    "fitness",
    "muscle",
    "strength",
    "macro",
    "calorie",
    "research",
    "hiit",
    "plan",
)


def default_topic_scope_judge(query: str) -> TopicScopeJudgement:
    query_lower = query.lower()
    is_fitness_related = any(keyword in query_lower for keyword in _FITNESS_TOPIC_KEYWORDS)
    return TopicScopeJudgement(
        decision="ALLOW" if is_fitness_related else "REJECT",
        requests=[
            ScopeRequest(
                text=query,
                action_type="fitness_education" if is_fitness_related else "other",
                supported=is_fitness_related,
            )
        ],
        reason="Keyword-based test stub verdict.",
    )


def default_user_intent_judge(query: str) -> UserIntentJudgement:
    query_lower = query.lower()
    if "research" in query_lower or "evidence" in query_lower or "study" in query_lower:
        intent = "research_question"
    elif "macro" in query_lower and ("check" in query_lower or "verify" in query_lower):
        intent = "verify_macros"
    elif "calculate" in query_lower and ("calorie" in query_lower or "tdee" in query_lower):
        intent = "calculate_calories"
    elif "swap" in query_lower or "edit" in query_lower or "change" in query_lower:
        intent = "edit_plan"
    elif "build" in query_lower or "create" in query_lower or "plan" in query_lower:
        intent = "build_plan"
    else:
        intent = "fitness_question"
    return UserIntentJudgement(
        intent=intent,
        reason="Keyword-based test stub verdict.",
        mentions_submitted_plan="here's my plan" in query_lower,
        touches_goal_or_constraints="goal" in query_lower,
    )
