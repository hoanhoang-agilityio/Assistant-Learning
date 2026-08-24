"""Tests for the ``notify_fail`` node."""

import pytest
from langchain_core.messages import AIMessage

from src.core.langgraph.nodes.notify_fail import (
    CHECK_SUMMARIES,
    NOTIFY_FAIL_INTRO,
    NOTIFY_FAIL_OUTRO,
    build_notify_fail_message,
    failed_checks,
    notify_fail,
)
from src.schemas import (
    CheckName,
    Severity,
    VerificationIssue,
    VerificationResult,
    initial_state,
)
from tests.test_verification_gate import USER_ID


def verdict(*issues: VerificationIssue) -> dict:
    """A failing verdict as the gate stores it in state."""
    return VerificationResult(issues=list(issues)).model_dump(mode="json")


def error(check: CheckName, message: str = "Fix it.") -> VerificationIssue:
    """One issue that fails the gate."""
    return VerificationIssue(check=check, message=message)


def state_after_the_gate(verification_result: dict | None) -> dict:
    """State as it stands when the gate gives up on the coach agent."""
    return initial_state("build me a plan", USER_ID) | {
        "verification_result": verification_result,
        "coach_retry_count": 3,
    }


def test_the_user_is_told_no_plan_is_coming() -> None:
    """Handing over a plan that failed the gate is the one thing this node prevents."""
    message = build_notify_fail_message(verdict(error(CheckName.MACROS)))

    assert message.startswith(NOTIFY_FAIL_INTRO)
    assert message.endswith(NOTIFY_FAIL_OUTRO)


def test_the_rules_that_failed_are_named_in_the_user_s_terms() -> None:
    """The issues are written at the coach agent; the user gets what went wrong instead."""
    message = build_notify_fail_message(
        verdict(
            error(CheckName.SAFETY, "Swap the overhead press for a landmine press.")
        )
    )

    assert CHECK_SUMMARIES[CheckName.SAFETY] in message
    assert "landmine" not in message


def test_a_rule_that_failed_repeatedly_is_named_once() -> None:
    """Eight unfilled slots are one thing wrong, not eight things to read."""
    message = build_notify_fail_message(
        verdict(*[error(CheckName.COMPLETENESS) for _ in range(3)])
    )

    assert message.count(CHECK_SUMMARIES[CheckName.COMPLETENESS]) == 1


def test_the_rules_are_named_in_the_order_they_ran() -> None:
    """The gate orders its issues for reading; re-ordering them here would undo that."""
    summaries = failed_checks(
        verdict(error(CheckName.COMPLETENESS), error(CheckName.SAFETY))
    )

    assert summaries == [
        CHECK_SUMMARIES[CheckName.COMPLETENESS],
        CHECK_SUMMARIES[CheckName.SAFETY],
    ]


def test_warnings_are_not_reported_as_reasons() -> None:
    """A warning never failed anything, so it cannot be why the run gave up."""
    warning = VerificationIssue(
        check=CheckName.VOLUME,
        message="Slightly under the weekly target.",
        severity=Severity.WARNING,
    )

    assert failed_checks(verdict(warning)) == []


@pytest.mark.parametrize(
    "verification_result", [None, {}, {"issues": [{"check": "nonsense"}]}]
)
def test_a_verdict_that_cannot_be_read_still_ends_the_run_cleanly(
    verification_result: dict | None,
) -> None:
    """The node is terminal: with nothing to list it must not trail off mid-sentence."""
    message = build_notify_fail_message(verification_result)

    assert message == f"{NOTIFY_FAIL_INTRO}\n\n{NOTIFY_FAIL_OUTRO}"


async def test_the_node_ends_the_run_with_the_notification() -> None:
    """A terminal node, so what it writes is what the caller shows."""
    result = verdict(error(CheckName.AVAILABILITY))

    update = await notify_fail(state_after_the_gate(result))

    expected = build_notify_fail_message(result)
    assert update["final_message"] == expected
    assert [message.content for message in update["messages"]] == [expected]
    assert isinstance(update["messages"][0], AIMessage)


async def test_the_rejected_plan_is_left_alone() -> None:
    """The user's stored plan is still theirs; a failed revision must not disturb it."""
    update = await notify_fail(state_after_the_gate(verdict(error(CheckName.MACROS))))

    assert "plan" not in update
