"""Tests for the deterministic gate as a whole: the rule set, its context, its verdict.

What each rule reports is covered in the sibling ``test_verification_*`` files. What is
covered here is everything around them — that every rule is registered and every rule runs,
that the context they read is resolved from the catalogue rather than from the agent, and
that the verdict routing depends on means what it says.
"""

import pytest

import src.core.langgraph.verification.deterministic.context as plan_context
from src.core.langgraph.verification import verify_plan
from src.core.langgraph.verification.deterministic import (
    RULES,
    PlanContext,
    build_plan_context,
    run_rules,
)
from src.enums import (
    MovementPattern,
    RestrictionAction,
)
from src.schemas import (
    CheckName,
    Exercise,
    Injury,
    MovementRestriction,
    Severity,
    TrainingPlan,
    UserProfile,
    VerificationIssue,
    VerificationResult,
    WorkoutTemplate,
)
from tests.test_verification_completeness import (
    CATALOGUE,
    PROFILE,
    TEMPLATE,
    complete_plan,
    day,
    plan_of,
)

# What the fixture plan's macros come to, so the macro rule stays quiet unless a test
# means it to fire.
BALANCED_CALORIES = 2114


def passing_plan() -> TrainingPlan:
    """A plan that satisfies every rule in the set."""
    return complete_plan().model_copy(update={"daily_calories": BALANCED_CALORIES})


def plan_broken_three_ways() -> TrainingPlan:
    """A plan with an unfilled slot and calories that disagree with its own macros."""
    return plan_of(
        day(1, "Upper", ("d1-s1", "ex-bench-press")),
        day(2, "Lower", ("d2-s1", "ex-back-squat")),
    )


def profile_with_shoulder(action: RestrictionAction) -> UserProfile:
    """The fixture user, with a shoulder injury the bench press runs into."""
    return PROFILE.model_copy(
        update={
            "injuries": [
                Injury(
                    body_part="shoulder",
                    restrictions=[
                        MovementRestriction(
                            movement_pattern=MovementPattern.HORIZONTAL_PUSH,
                            action=action,
                        )
                    ],
                )
            ]
        }
    )


def context_for(plan: TrainingPlan, profile: UserProfile = PROFILE) -> PlanContext:
    """A resolved context over the fixture template and catalogue."""
    return PlanContext(
        plan=plan, profile=profile, template=TEMPLATE, exercises=CATALOGUE
    )


# --- The rule set -------------------------------------------------------------------------


def test_there_is_one_registered_rule_per_check() -> None:
    """A rule written but never added to ``RULES`` is a check nobody runs."""
    assert len(RULES) == len(CheckName)
    assert len(set(RULES)) == len(RULES)


def test_every_rule_stays_quiet_on_a_good_plan() -> None:
    """One noisy rule fails every plan, so each is asked on its own as well."""
    context = context_for(passing_plan())

    assert {rule.__name__: rule(context) for rule in RULES} == {
        rule.__name__: [] for rule in RULES
    }


def test_a_plan_broken_several_ways_is_reported_in_full() -> None:
    """Stopping at the first failure would spend the retry budget one fix at a time."""
    result = run_rules(
        context_for(
            plan_broken_three_ways(),
            profile_with_shoulder(RestrictionAction.PROHIBITED),
        )
    )

    assert {issue.check for issue in result.errors} == {
        CheckName.COMPLETENESS,
        CheckName.MACROS,
        CheckName.SAFETY,
    }


def test_the_issues_come_back_in_the_order_the_rules_ran() -> None:
    """The order is what the coach agent reads: what is missing, wrong, then unsafe."""
    result = run_rules(
        context_for(
            plan_broken_three_ways(),
            profile_with_shoulder(RestrictionAction.PROHIBITED),
        )
    )

    assert [issue.check for issue in result.issues] == [
        CheckName.COMPLETENESS,
        CheckName.MACROS,
        CheckName.SAFETY,
    ]


def test_a_good_plan_comes_back_with_nothing_to_say() -> None:
    """Every rule has to stay quiet on a good plan, or the gate fails every plan."""
    result = run_rules(context_for(passing_plan()))

    assert result.issues == []
    assert result.passed


def test_a_warning_is_collected_without_failing_the_plan() -> None:
    """A limited movement is worth telling the agent about, not worth a retry over."""
    result = run_rules(
        context_for(passing_plan(), profile_with_shoulder(RestrictionAction.LIMITED))
    )

    assert [issue.severity for issue in result.issues] == [Severity.WARNING]
    assert result.passed


# --- The resolved context -----------------------------------------------------------------


@pytest.fixture
def catalogue(monkeypatch: pytest.MonkeyPatch) -> list[list[str]]:
    """Serve the fixture rows without a database, recording what was asked for."""
    requested: list[list[str]] = []

    async def fetch_template(template_id: str) -> WorkoutTemplate | None:
        return TEMPLATE if template_id == TEMPLATE.id else None

    async def fetch_exercises_by_id(exercise_ids: list[str]) -> dict[str, Exercise]:
        requested.append(exercise_ids)
        return {
            exercise_id: CATALOGUE[exercise_id]
            for exercise_id in exercise_ids
            if exercise_id in CATALOGUE
        }

    monkeypatch.setattr(plan_context, "fetch_template", fetch_template)
    monkeypatch.setattr(plan_context, "fetch_exercises_by_id", fetch_exercises_by_id)
    return requested


async def test_the_context_is_resolved_from_the_catalogue(
    catalogue: list[list[str]],
) -> None:
    """The gate re-reads what it checks: trusting the agent's tool calls checks nothing."""
    plan = passing_plan()

    context = await build_plan_context(plan, PROFILE)

    assert context.template == TEMPLATE
    assert context.plan is plan
    assert context.profile is PROFILE


async def test_every_prescribed_exercise_is_looked_up(
    catalogue: list[list[str]],
) -> None:
    """A row that is never fetched is a movement no rule can check."""
    plan = passing_plan()

    await build_plan_context(plan, PROFILE)

    [asked_for] = catalogue
    assert sorted(asked_for) == sorted(
        exercise.exercise_id for exercise in plan.planned_exercises()
    )


async def test_a_template_that_does_not_exist_resolves_to_nothing(
    catalogue: list[list[str]],
) -> None:
    """The completeness rule reports the missing template; this must not raise first."""
    plan = passing_plan().model_copy(update={"template_id": "tpl-invented"})

    context = await build_plan_context(plan, PROFILE)

    assert context.template is None


async def test_an_invented_exercise_is_simply_absent(
    catalogue: list[list[str]],
) -> None:
    """The gap is how the rules recognise an invented movement, so it cannot raise."""
    plan = plan_of(
        day(1, "Upper", ("d1-s1", "ex-invented"), ("d1-s2", "ex-cable-row")),
        day(2, "Lower", ("d2-s1", "ex-back-squat")),
    )

    context = await build_plan_context(plan, PROFILE)

    assert context.exercise_for("ex-invented") is None
    assert context.exercise_for("ex-cable-row") == CATALOGUE["ex-cable-row"]


# --- The verdict --------------------------------------------------------------------------


def test_an_issue_fails_the_gate_unless_it_says_otherwise() -> None:
    """A rule that forgets to set a severity must not quietly let a plan through."""
    issue = VerificationIssue(check=CheckName.SAFETY, message="Something is wrong.")

    assert issue.severity is Severity.ERROR


def test_a_result_holding_an_error_cannot_claim_to_pass() -> None:
    """``passed`` is derived rather than set: the routing depends on that invariant."""
    result = VerificationResult(
        issues=[VerificationIssue(check=CheckName.MACROS, message="Wrong.")]
    )

    assert not result.passed


def test_errors_and_warnings_are_told_apart() -> None:
    """Only errors send the plan back; a warning that did would strand the user."""
    error = VerificationIssue(check=CheckName.MACROS, message="Wrong.")
    warning = VerificationIssue(
        check=CheckName.VOLUME, message="A little light.", severity=Severity.WARNING
    )

    result = VerificationResult(issues=[error, warning])

    assert result.errors == [error]
    assert result.warnings == [warning]
    assert not result.passed


def test_warnings_alone_leave_the_gate_open() -> None:
    """Sending a plan back over a warning three times would leave the user with none."""
    result = VerificationResult(
        issues=[
            VerificationIssue(
                check=CheckName.VOLUME,
                message="A little light.",
                severity=Severity.WARNING,
            )
        ]
    )

    assert result.passed


def test_a_verdict_on_nothing_passes() -> None:
    """No rule fired, so there is nothing to send back."""
    assert VerificationResult().passed


# --- End to end ---------------------------------------------------------------------------


async def test_a_good_plan_passes_the_whole_gate(catalogue: list[list[str]]) -> None:
    """The path a plan takes to the user, with nothing stubbed but the database."""
    result = await verify_plan(passing_plan(), PROFILE)

    assert result.passed
    assert result.issues == []


async def test_a_bad_plan_fails_the_whole_gate(catalogue: list[list[str]]) -> None:
    """The same path for a plan that must not reach the user."""
    result = await verify_plan(
        plan_broken_three_ways(), profile_with_shoulder(RestrictionAction.PROHIBITED)
    )

    assert not result.passed
    assert {issue.check for issue in result.errors} == {
        CheckName.COMPLETENESS,
        CheckName.MACROS,
        CheckName.SAFETY,
    }
