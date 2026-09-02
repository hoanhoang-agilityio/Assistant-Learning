"""The ``notify_fail`` node: tell the user no plan passed verification, and stop."""

from langchain_core.messages import AIMessage, AnyMessage
from pydantic import ValidationError

from src.schemas import (
    CheckName,
    GraphState,
    VerificationCycleReset,
    VerificationResult,
    cleared_verification,
)

NOTIFY_FAIL_INTRO = (
    "I put together a plan for you, but it didn't pass all of my safety and "
    "quality checks. I'd rather pause and make sure I get it right than give "
    "you a plan I'm not confident in."
)

NOTIFY_FAIL_CHECKS_INTRO = "Here's what I still need to get right:"

NOTIFY_FAIL_OUTRO = (
    "No worries — nothing has been saved, and your current plan is still untouched. "
    "Tell me a little more about what you're looking for, such as your equipment, "
    "schedule, or anything you'd like me to work around, and I'll give it another try!"
)

CHECK_SUMMARIES: dict[CheckName, str] = {
    CheckName.COMPLETENESS: "the plan came out incomplete",
    CheckName.MACROS: "the calorie and macro targets didn't add up",
    CheckName.VOLUME: "the training volume didn't fit the days you train",
    CheckName.AVAILABILITY: "some exercises needed equipment you don't have",
    CheckName.SAFETY: "some exercises clashed with an injury on your profile",
}


class NotifyFailUpdate(VerificationCycleReset):
    """The state ``notify_fail`` writes."""

    messages: list[AnyMessage]


def failed_checks(verification_result: dict | None) -> list[str]:
    """Summarise each rule that failed, once each, in the order the rules ran."""

    if not verification_result:
        return []

    try:
        result = VerificationResult.model_validate(verification_result)
    except ValidationError:
        return []

    return list(
        dict.fromkeys(
            CHECK_SUMMARIES[issue.check]
            for issue in result.errors
            if issue.check in CHECK_SUMMARIES
        )
    )


def build_notify_fail_message(verification_result: dict | None) -> str:
    """Compose the message that ends a run no plan came out of."""

    summaries = failed_checks(verification_result)
    if not summaries:
        return f"{NOTIFY_FAIL_INTRO}\n\n{NOTIFY_FAIL_OUTRO}"

    bullets = "\n".join(f"- {summary}" for summary in summaries)
    return (
        f"{NOTIFY_FAIL_INTRO}\n\n{NOTIFY_FAIL_CHECKS_INTRO}\n{bullets}\n\n"
        f"{NOTIFY_FAIL_OUTRO}"
    )


async def notify_fail(state: GraphState) -> NotifyFailUpdate:
    """End the coaching branch after the plan failed verification too many times."""

    message = build_notify_fail_message(state.get("verification_result"))

    return {**cleared_verification(), "messages": [AIMessage(content=message)]}
