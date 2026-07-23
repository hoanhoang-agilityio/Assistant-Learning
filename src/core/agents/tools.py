from core.agents.request_type_judge import judge_request_type
from core.agents.state import AffectedDomain, RequestType, ScopeResult
from core.agents.topic_scope_judge import judge_topic_scope
from core.config.settings import get_settings

OFF_TOPIC_REFUSAL_MESSAGE = (
    "I'm your fitness planning assistant, so I can only help with "
    "training, workouts, nutrition/macros, and related fitness goals. "
    "Could you rephrase your question around a fitness goal, like a "
    "workout plan, macro targets, or training advice?"
)

CLARIFY_MESSAGE = (
    "I'm not sure yet what you'd like help with -- could you share a fitness "
    "goal or what you'd like me to build, like a workout plan, macro targets, "
    "or recovery advice? Send a new message with a bit more detail."
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


def check_topic_scope(query: str) -> ScopeResult:
    """Classify the fitness/nutrition scope of a query via an LLM judge.

    This is the translation boundary between the judge's own output contract
    (TopicScopeJudgement, topic_scope_judge.py) and the orchestration-level
    ScopeResult persisted in state: it partitions `judgement.requests` into
    supported/unsupported here so the judge's schema can evolve independently
    of what gets checkpointed.

    `decision` is the sole routing signal callers should act on (see
    supervisor.py):

    - ALLOW: every actionable request is supported -- the caller should
      proceed with the original query untouched.
    - REJECT: no actionable request is supported (this also covers a message
      that only wraps an unsupported ask in fitness-sounding context, e.g.
      "I want to train at the beach, give me the weather of Danang city" --
      "train at the beach" isn't itself a request, so the only actionable
      request is the unsupported weather lookup) -- the caller should
      terminate the run.
    - CLARIFY: no concrete actionable request yet -- the caller should
      terminate the run the same as REJECT (see refusal_message_for for the
      distinct copy); the user is expected to start a new message, not
      resume this run.
    - MIXED: a genuinely separate supported request and unsupported request
      both present -- the caller should terminate the run rather than
      silently continuing with only the supported part. supported_requests/
      unsupported_requests are preserved on the result so the unsupported
      ask is never silently discarded from logs/UI even though the run
      never reaches planning.
    """
    judgement = judge_topic_scope(query)
    return ScopeResult(
        decision=judgement.decision,
        supported_requests=[request for request in judgement.requests if request.supported],
        unsupported_requests=[request for request in judgement.requests if not request.supported],
        reason=judgement.reason,
    )


def refusal_message_for(scope_result: ScopeResult) -> str | None:
    """User-facing copy for a non-ALLOW scope decision. None for ALLOW."""
    if scope_result.decision == "ALLOW":
        return None
    if scope_result.decision == "REJECT":
        return OFF_TOPIC_REFUSAL_MESSAGE
    if scope_result.decision == "CLARIFY":
        return CLARIFY_MESSAGE

    # MIXED: name the specific parts so the user knows what to resend, rather than a
    # generic refusal -- the structured supported/unsupported lists already exist, so
    # not using them here would waste the one part of this that's user-facing.
    supported = "; ".join(request.text for request in scope_result.supported_requests)
    unsupported = "; ".join(request.text for request in scope_result.unsupported_requests)
    return (
        f'I can help with your fitness request ("{supported}"), '
        f'but I can\'t assist with unrelated requests such as "{unsupported}". '
        "Please resend only your fitness-related request, and I'll be happy to help."
    )


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
