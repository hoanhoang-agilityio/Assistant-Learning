from core.orchestration.agents.state import ScopeResult
from core.orchestration.agents.topic_scope_judge import judge_topic_scope

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


def check_topic_scope(query: str) -> ScopeResult:
    judgement = judge_topic_scope(query)
    return ScopeResult(
        decision=judgement.decision,
        supported_requests=[request for request in judgement.requests if request.supported],
        unsupported_requests=[request for request in judgement.requests if not request.supported],
        reason=judgement.reason,
    )


def refusal_message_for(scope_result: ScopeResult) -> str | None:
    if scope_result.decision == "ALLOW":
        return None
    if scope_result.decision == "REJECT":
        return OFF_TOPIC_REFUSAL_MESSAGE
    if scope_result.decision == "CLARIFY":
        return CLARIFY_MESSAGE
    supported = "; ".join(request.text for request in scope_result.supported_requests)
    unsupported = "; ".join(request.text for request in scope_result.unsupported_requests)
    return (
        f'I can help with your fitness request ("{supported}"), '
        f'but I can\'t assist with unrelated requests such as "{unsupported}". '
        "Please resend only your fitness-related request, and I'll be happy to help."
    )
