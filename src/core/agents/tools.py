import logging

from core.agents.state import AffectedDomain, RequestType
from core.agents.topic_scope_judge import judge_topic_scope
from core.config.settings import get_settings

logger = logging.getLogger(__name__)

# Broad allowlist for the topic-scope guardrail (check_topic_scope): if a
# query matches none of these, it's treated as outside the fitness/nutrition
# domain and refused before classification/routing. Intentionally broad
# (favors false negatives over blocking real fitness questions phrased in
# unusual ways) since this is a coarse pre-check, not a full classifier.
FITNESS_TOPIC_KEYWORDS: tuple[str, ...] = (
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

OFF_TOPIC_REFUSAL_MESSAGE = (
    "I'm your fitness planning assistant, so I can only help with "
    "training, workouts, nutrition/macros, and related fitness goals. "
    "Could you rephrase your question around a fitness goal, like a "
    "workout plan, macro targets, or training advice?"
)

REQUEST_TYPE_KEYWORDS: list[tuple[RequestType, tuple[str, ...]]] = [
    ("fat_loss", ("lose weight", "fat loss", "cutting", "cut ")),
    ("muscle_gain", ("muscle gain", "bulk", "hypertrophy", "build muscle")),
    ("macro_calculation", ("macro", "calories", "protein", "macros")),
    ("strength", ("strength", "powerlifting", "1rm")),
    ("endurance", ("endurance", "marathon", "cardio")),
    ("training_plan", ("training plan", "workout plan", "program")),
]

DEFAULT_AFFECTED_DOMAINS: list[AffectedDomain] = [
    "planning",
    "research",
    "fitness",
    "verify",
]

# Per-request_type narrower domain set, used only when
# settings.classify_request_narrows_domains is true. Empty by construction:
# no request_type is currently known to be safe to narrow (e.g.
# macro_calculation still needs "research" per planning_agent.py's prompt),
# so populating this without also updating that prompt would cause the
# planning agent to plan work the pipeline then never runs. See
# docs/reports/known_limitations_remediation_plan.md, "Issue 2 (part 2)".
REQUEST_TYPE_DOMAIN_OVERRIDES: dict[RequestType, list[AffectedDomain]] = {}


def check_topic_scope(query: str) -> dict:
    """Flag queries outside the fitness/nutrition domain (keyword pre-check + optional LLM fallback)."""
    query_lower = query.lower()
    is_off_topic = not any(keyword in query_lower for keyword in FITNESS_TOPIC_KEYWORDS)

    if is_off_topic and get_settings().topic_scope_llm_fallback_enabled:
        try:
            judgement = judge_topic_scope(query)
            is_off_topic = not judgement.is_fitness_related
        except Exception:
            # Fail safe to the keyword verdict (refuse) rather than let a
            # judge/API outage either block every off-topic-looking query
            # from ever being rescued, or crash the run.
            logger.warning(
                "topic_scope_judge fallback failed; using keyword verdict", exc_info=True
            )

    return {
        "is_off_topic": is_off_topic,
        "refusal_message": OFF_TOPIC_REFUSAL_MESSAGE if is_off_topic else None,
    }


def classify_request(query: str) -> dict:
    """Classify request into request_type and affected_domains."""
    query_lower = query.lower()
    request_type: RequestType = "general_fitness"

    for candidate_type, keywords in REQUEST_TYPE_KEYWORDS:
        if any(keyword in query_lower for keyword in keywords):
            request_type = candidate_type
            break

    affected_domains = list(DEFAULT_AFFECTED_DOMAINS)
    if get_settings().classify_request_narrows_domains:
        override = REQUEST_TYPE_DOMAIN_OVERRIDES.get(request_type)
        if override is not None:
            affected_domains = list(override)

    return {
        "request_type": request_type,
        "affected_domains": affected_domains,
    }
