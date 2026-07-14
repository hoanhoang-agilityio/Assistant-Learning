from core.agents.request_type_judge import judge_request_type
from core.agents.state import AffectedDomain, RequestType
from core.agents.topic_scope_judge import judge_topic_scope
from core.config.settings import get_settings

OFF_TOPIC_REFUSAL_MESSAGE = (
    "I'm your fitness planning assistant, so I can only help with "
    "training, workouts, nutrition/macros, and related fitness goals. "
    "Could you rephrase your question around a fitness goal, like a "
    "workout plan, macro targets, or training advice?"
)

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
    """Flag queries outside the fitness/nutrition domain via an LLM judge."""
    judgement = judge_topic_scope(query)
    is_off_topic = not judgement.is_fitness_related

    return {
        "is_off_topic": is_off_topic,
        "refusal_message": OFF_TOPIC_REFUSAL_MESSAGE if is_off_topic else None,
    }


def classify_request(query: str) -> dict:
    """Classify request into request_type and affected_domains via an LLM judge."""
    judgement = judge_request_type(query)
    request_type = judgement.request_type

    affected_domains = list(DEFAULT_AFFECTED_DOMAINS)
    if get_settings().classify_request_narrows_domains:
        override = REQUEST_TYPE_DOMAIN_OVERRIDES.get(request_type)
        if override is not None:
            affected_domains = list(override)

    return {
        "request_type": request_type,
        "affected_domains": affected_domains,
    }
