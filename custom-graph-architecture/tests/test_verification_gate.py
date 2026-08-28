"""Tests for the ``deterministic_verification`` node: the verdict, the counter, the route.

The rules themselves are covered per-rule elsewhere. What matters here is what the node
does with their verdict: what it writes for the coach agent, how many times the coach is
sent back, and where the run goes when the budget is gone.
"""

import json

import pytest

import src.nodes.verification as verification_node
import src.verification.deterministic.context as plan_context
from src.configs.config import settings
from src.nodes.verification import (
    NO_PLAN_MESSAGE,
    UNVERIFIABLE_PROFILE_MESSAGE,
    deterministic_verification,
    route_after_verification,
)
from src.schemas import (
    CheckName,
    Exercise,
    Severity,
    TrainingPlan,
    VerificationIssue,
    VerificationResult,
    WorkoutTemplate,
    initial_state,
)
from tests.test_verification_completeness import (
    CATALOGUE,
    PROFILE,
    TEMPLATE,
    complete_plan,
    day,
    plan_of,
)

USER_ID = "user-verification"

# What the fixture plan's macros actually come to, so the macro rule stays quiet and the
# gate's verdict is about the plan being tested rather than about its calories.
BALANCED_CALORIES = 2114


def passing_plan() -> TrainingPlan:
    """A plan that satisfies every deterministic rule."""
    return complete_plan().model_copy(update={"daily_calories": BALANCED_CALORIES})


def failing_plan() -> TrainingPlan:
    """The same plan with a template slot left unfilled."""
    return plan_of(
        day(1, "Upper", ("d1-s1", "ex-bench-press")),
        day(2, "Lower", ("d2-s1", "ex-back-squat")),
    ).model_copy(update={"daily_calories": BALANCED_CALORIES})


def state_after_coach(plan: TrainingPlan | None = None, **overrides: object) -> dict:
    """State as it stands when ``coach_agent`` hands its plan to the gate."""
    return (
        initial_state("build me a plan", USER_ID)
        | {
            "profile": PROFILE.model_dump(mode="json"),
            "plan": plan.model_dump(mode="json") if plan else None,
        }
        | overrides
    )


@pytest.fixture
def catalogue(monkeypatch: pytest.MonkeyPatch) -> None:
    """Serve the fixture template and exercises so the real rules run without a database."""

    async def fetch_template(template_id: str) -> WorkoutTemplate | None:
        return TEMPLATE if template_id == TEMPLATE.id else None

    async def fetch_exercises_by_id(exercise_ids: list[str]) -> dict[str, Exercise]:
        return {
            exercise_id: CATALOGUE[exercise_id]
            for exercise_id in exercise_ids
            if exercise_id in CATALOGUE
        }

    monkeypatch.setattr(plan_context, "fetch_template", fetch_template)
    monkeypatch.setattr(plan_context, "fetch_exercises_by_id", fetch_exercises_by_id)


# --- The verdict ------------------------------------------------------------------------


async def test_a_plan_that_breaks_no_rule_clears_the_gate(catalogue: None) -> None:
    """Nothing to fix is what a pass looks like: the coach must not be handed a rejection."""
    update = await deterministic_verification(state_after_coach(passing_plan()))

    assert update == {"verification_result": None, "coach_retry_count": 0}


async def test_a_failing_plan_is_returned_with_what_to_fix(catalogue: None) -> None:
    """The gate exists to send the plan back, and the agent can only act on the reasons."""
    update = await deterministic_verification(state_after_coach(failing_plan()))

    issues = update["verification_result"]["issues"]
    assert [issue["check"] for issue in issues] == [CheckName.COMPLETENESS]
    assert issues[0]["slot_id"] == "d1-s2"


async def test_the_verdict_survives_the_checkpoint(catalogue: None) -> None:
    """State is checkpointed to Postgres, so a verdict holding enums would not persist."""
    update = await deterministic_verification(state_after_coach(failing_plan()))

    assert (
        json.loads(json.dumps(update["verification_result"]))
        == (update["verification_result"])
    )


async def test_a_warning_alone_does_not_fail_the_gate(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Warnings are advice for the agent; failing on them would strand the user."""

    async def warn_only(*args: object, **kwargs: object) -> VerificationResult:
        return VerificationResult(
            issues=[
                VerificationIssue(
                    check=CheckName.SAFETY,
                    message="A stated preference was ignored.",
                    severity=Severity.WARNING,
                )
            ]
        )

    monkeypatch.setattr(verification_node, "verify_plan", warn_only)

    update = await deterministic_verification(state_after_coach(passing_plan()))

    assert update == {"verification_result": None, "coach_retry_count": 0}


# --- Plans the rules cannot be run on -----------------------------------------------------


async def test_no_plan_at_all_fails_the_gate() -> None:
    """``coach_agent`` returns no plan when it fails; nothing may pass on an empty plan."""
    update = await deterministic_verification(state_after_coach(None))

    [issue] = update["verification_result"]["issues"]
    assert issue["message"] == NO_PLAN_MESSAGE
    assert update["coach_retry_count"] == 1


async def test_a_plan_that_is_not_a_plan_fails_the_gate() -> None:
    """A resumed checkpoint can hold anything; an unparseable plan is not a passing one."""
    update = await deterministic_verification(
        state_after_coach() | {"plan": {"template_id": "tpl-upper-lower"}}
    )

    assert update["verification_result"]["issues"][0]["field"] == "plan"
    assert update["coach_retry_count"] == 1


async def test_an_unreadable_profile_fails_the_gate_unchecked(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """With no user to check the plan against, the rules have nothing to say about it."""

    async def fail(*args: object, **kwargs: object) -> None:
        raise AssertionError("the rules must not run without a profile to run them for")

    monkeypatch.setattr(verification_node, "verify_plan", fail)

    update = await deterministic_verification(
        state_after_coach(passing_plan()) | {"profile": {"age": 34}}
    )

    [issue] = update["verification_result"]["issues"]
    assert issue["message"] == UNVERIFIABLE_PROFILE_MESSAGE


# --- The retry counter --------------------------------------------------------------------


async def test_each_failed_attempt_is_counted(catalogue: None) -> None:
    """The counter is what bounds the loop; a failure that does not count never ends it."""
    update = await deterministic_verification(
        state_after_coach(failing_plan(), coach_retry_count=1)
    )

    assert update["coach_retry_count"] == 2


async def test_a_pass_clears_the_count(catalogue: None) -> None:
    """A reviewer's revision re-enters the gate: a stale count would exhaust it at once."""
    update = await deterministic_verification(
        state_after_coach(passing_plan(), coach_retry_count=2)
    )

    assert update["coach_retry_count"] == 0


# --- Routing ------------------------------------------------------------------------------


def test_a_cleared_verdict_routes_to_review() -> None:
    """The only way past the gate."""
    assert route_after_verification(state_after_coach()) == "pass"


@pytest.mark.parametrize(
    ("retry_count", "expected"),
    [
        (0, "retry"),
        (settings.COACH_MAX_RETRIES - 1, "retry"),
        (settings.COACH_MAX_RETRIES, "exhausted"),
        (settings.COACH_MAX_RETRIES + 1, "exhausted"),
    ],
)
def test_a_failed_verdict_routes_on_the_budget(retry_count: int, expected: str) -> None:
    """Back to the coach while there are attempts left, and to ``notify_fail`` after."""
    state = state_after_coach(
        coach_retry_count=retry_count,
        verification_result={"issues": [{"check": "completeness"}]},
    )

    assert route_after_verification(state) == expected


async def test_the_coach_is_sent_back_a_bounded_number_of_times(
    catalogue: None,
) -> None:
    """The loop the spec bounds: the plan never improves, so the run has to give up."""
    state = state_after_coach(failing_plan())
    routes = []

    for _ in range(settings.COACH_MAX_RETRIES):
        state |= await deterministic_verification(state)
        routes.append(route_after_verification(state))

    assert routes == ["retry"] * (settings.COACH_MAX_RETRIES - 1) + ["exhausted"]
