from pathlib import Path

import pytest
from pydantic import ValidationError

from core.agents.intent_judge import UserIntentJudgement
from core.agents.run_execution_plan import (
    WORKFLOW_TEMPLATES,
    RunExecutionPlan,
    resolve_workflow,
)
from core.agents.state import OrchestrationState
from core.config.settings import get_settings
from core.graph.run import create_initial_state


def _plan(**overrides: object) -> RunExecutionPlan:
    defaults: dict[str, object] = {
        "user_intent": "generate",
        "workflow": "GenerateWorkflow",
        "ordered_domains": ["planning", "research", "fitness", "verify"],
        "fitness_mode": "generate",
        "verification_strategy": "FULL",
    }
    defaults.update(overrides)
    return RunExecutionPlan(**defaults)


def test_round_trips_through_model_dump_and_validate() -> None:
    plan = _plan()
    restored = RunExecutionPlan.model_validate(plan.model_dump())
    assert restored == plan


def test_model_dump_contains_exactly_the_five_stored_fields() -> None:
    """Regression guard for design review F6: entry_domain/requires_profile must never
    become stored/serialized fields again."""
    dumped = _plan().model_dump()
    assert set(dumped.keys()) == {
        "user_intent",
        "workflow",
        "ordered_domains",
        "fitness_mode",
        "verification_strategy",
    }


@pytest.mark.parametrize(
    ("ordered_domains", "expected_entry", "expected_requires_profile"),
    [
        (["planning", "research", "fitness", "verify"], "planning", True),
        (["fitness", "verify"], "fitness", True),
        (["verify"], "verify", False),
    ],
)
def test_entry_domain_and_requires_profile_are_computed(
    ordered_domains: list[str],
    expected_entry: str,
    expected_requires_profile: bool,
) -> None:
    plan = _plan(ordered_domains=ordered_domains)
    assert plan.entry_domain == expected_entry
    assert plan.requires_profile is expected_requires_profile


def test_plan_is_frozen() -> None:
    plan = _plan()
    with pytest.raises(ValidationError):
        plan.workflow = "EditWorkflow"  # type: ignore[misc]


def test_rejects_unknown_fields() -> None:
    with pytest.raises(ValidationError):
        RunExecutionPlan(
            user_intent="generate",
            workflow="GenerateWorkflow",
            ordered_domains=["planning"],
            fitness_mode="generate",
            verification_strategy="FULL",
            not_a_real_field="oops",
        )


def test_orchestration_state_carries_execution_plan_field(tmp_path: Path) -> None:
    state: OrchestrationState = create_initial_state(
        run_id="phase1-run",
        thread_id="phase1-thread",
        query="test query",
        workspace_root=tmp_path / "workspace",
    )
    assert "execution_plan" in state
    assert state["execution_plan"] is None


def test_run_execution_plan_enabled_flag_defaults_off() -> None:
    assert get_settings().run_execution_plan_enabled is False


def _judgement(**overrides: object) -> UserIntentJudgement:
    defaults: dict[str, object] = {
        "user_intent": "generate",
        "reason": "stub",
        "mentions_submitted_plan": False,
        "touches_goal_or_constraints": False,
    }
    defaults.update(overrides)
    return UserIntentJudgement(**defaults)


def test_workflow_templates_registry_has_all_four_workflows() -> None:
    assert set(WORKFLOW_TEMPLATES.keys()) == {
        "GenerateWorkflow",
        "EditWorkflow",
        "EditWithReplanWorkflow",
        "VerifyExternalWorkflow",
    }


def test_resolve_workflow_generate() -> None:
    plan = resolve_workflow(_judgement(user_intent="generate"))
    assert plan.workflow == "GenerateWorkflow"
    assert plan.ordered_domains == ["planning", "research", "fitness", "verify"]
    assert plan.fitness_mode == "generate"
    assert plan.verification_strategy == "FULL"


def test_resolve_workflow_verify() -> None:
    plan = resolve_workflow(_judgement(user_intent="verify", mentions_submitted_plan=True))
    assert plan.workflow == "VerifyExternalWorkflow"
    assert plan.ordered_domains == ["fitness", "verify"]
    assert plan.fitness_mode == "evaluate"
    assert plan.verification_strategy == "EXTERNAL_PLAN"


def test_resolve_workflow_edit_workout_only() -> None:
    plan = resolve_workflow(_judgement(user_intent="edit", touches_goal_or_constraints=False))
    assert plan.workflow == "EditWorkflow"
    assert plan.ordered_domains == ["fitness", "verify"]
    assert plan.fitness_mode == "edit"
    assert plan.verification_strategy == "EDIT_REVIEW"


def test_resolve_workflow_edit_touches_goal_or_constraints() -> None:
    plan = resolve_workflow(_judgement(user_intent="edit", touches_goal_or_constraints=True))
    assert plan.workflow == "EditWithReplanWorkflow"
    assert plan.ordered_domains == ["planning", "fitness", "verify"]
    assert plan.fitness_mode == "edit"
    assert plan.verification_strategy == "EDIT_REVIEW"


def test_resolve_workflow_copies_template_domains_not_shared_reference() -> None:
    """A mutation of one resolved plan's ordered_domains must never corrupt the shared
    WorkflowTemplate or a different run's plan built from the same template."""
    plan_a = resolve_workflow(_judgement(user_intent="generate"))
    plan_b = resolve_workflow(_judgement(user_intent="generate"))
    assert plan_a.ordered_domains is not plan_b.ordered_domains
    assert plan_a.ordered_domains is not WORKFLOW_TEMPLATES["GenerateWorkflow"].ordered_domains
