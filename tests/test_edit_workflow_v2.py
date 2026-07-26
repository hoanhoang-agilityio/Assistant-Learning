import json
from pathlib import Path
from typing import Any

import pytest

from core.agents.intent_judge import UserIntentJudgement, configure_user_intent_judge
from core.agents.state import OrchestrationState
from core.agents.supervisor import supervisor_node
from core.config.settings import get_settings
from core.graph.run import create_initial_state
from core.profile.goal_spec import derive_goal_spec
from core.subgraphs.fitness.blueprint import build_plan_blueprint
from core.subgraphs.fitness.template_registry import resolve_workout_template
from core.vfs import VFS
from tests.test_supervisor_graph import (  # noqa: F401 -- reuse existing stub helper
    _configure_generate_classification_stubs,
)


@pytest.fixture
def complete_profile() -> dict[str, Any]:
    return {
        "age": 30,
        "sex": "male",
        "height_cm": 175,
        "current_weight_kg": 85.0,
        "activity_level": "gym_3x_week",
        "goal": "fat_loss",
        "days_per_week": 3,
    }


# --- template_registry.py: fitness_mode vs revision_feedback ---------------------------


def test_resolve_workout_template_flag_off_uses_legacy_revision_feedback(
    tmp_path: Path, complete_profile: dict[str, Any], monkeypatch: pytest.MonkeyPatch
) -> None:
    """Regression: edit_workflow_v2_enabled off preserves today's exact behavior --
    fitness_mode is never consulted."""
    monkeypatch.setenv("EDIT_WORKFLOW_V2_ENABLED", "false")
    get_settings.cache_clear()
    workspace_path = str(tmp_path / "workspace")
    VFS.for_run(Path(workspace_path))  # ensure workspace exists
    blueprint = build_plan_blueprint(
        complete_profile,
        {"days_per_week": 3, "equipment": "gym"},
        derive_goal_spec(complete_profile),
    )

    result = resolve_workout_template(
        workspace_path=workspace_path,
        profile=complete_profile,
        constraints={"days_per_week": 3, "equipment": "gym"},
        blueprint=blueprint,
        planner_feedback=[],
        verification_feedback=None,
        is_verification_rerun=False,
        fitness_mode="edit",  # must be ignored -- flag is off
    )
    # No revision_feedback on disk and fitness_mode is ignored -- falls through to a
    # normal generation attempt (llm_required), not an edit path.
    assert "edit_operation" not in result


def test_resolve_workout_template_flag_on_uses_fitness_mode(
    tmp_path: Path, complete_profile: dict[str, Any], monkeypatch: pytest.MonkeyPatch
) -> None:
    """fitness_mode == "edit" is authoritative when the flag is on -- even with no
    revision_feedback on disk, a prior workout present means the edit path is attempted
    (and gracefully falls back to generation only because there's no revision text)."""
    monkeypatch.setenv("EDIT_WORKFLOW_V2_ENABLED", "true")
    get_settings.cache_clear()
    workspace_path = str(tmp_path / "workspace")
    blueprint = build_plan_blueprint(
        complete_profile,
        {"days_per_week": 3, "equipment": "gym"},
        derive_goal_spec(complete_profile),
    )

    result = resolve_workout_template(
        workspace_path=workspace_path,
        profile=complete_profile,
        constraints={"days_per_week": 3, "equipment": "gym"},
        blueprint=blueprint,
        planner_feedback=[],
        verification_feedback=None,
        is_verification_rerun=False,
        fitness_mode="generate",
    )
    # fitness_mode == "generate" (not "edit") -- edit path never attempted, identical to
    # flag-off's generate case.
    assert "edit_operation" not in result
    assert result["workout_source"] == "llm_required"


def test_resolve_workout_template_flag_on_no_prior_workout_falls_back_to_generation(
    tmp_path: Path, complete_profile: dict[str, Any], monkeypatch: pytest.MonkeyPatch
) -> None:
    """The currently-unreachable-in-practice case (design review F1): fitness_mode=="edit"
    on a fresh run with no prior plan degrades gracefully to generation, never crashes."""
    monkeypatch.setenv("EDIT_WORKFLOW_V2_ENABLED", "true")
    get_settings.cache_clear()
    workspace_path = str(tmp_path / "workspace")
    blueprint = build_plan_blueprint(
        complete_profile,
        {"days_per_week": 3, "equipment": "gym"},
        derive_goal_spec(complete_profile),
    )

    result = resolve_workout_template(
        workspace_path=workspace_path,
        profile=complete_profile,
        constraints={"days_per_week": 3, "equipment": "gym"},
        blueprint=blueprint,
        planner_feedback=[],
        verification_feedback=None,
        is_verification_rerun=False,
        fitness_mode="edit",
    )
    assert result["structured_workout"] is None
    assert result["workout_source"] == "llm_required"
    assert "edit_operation" not in result


# --- supervisor.py: EditWorkflow storage/fallback ---------------------------------------


@pytest.fixture
def initial_state(tmp_path: Path) -> OrchestrationState:
    state = create_initial_state(
        run_id="edit-v2-run",
        thread_id="edit-v2-thread",
        query="change my plan",
        workspace_root=tmp_path / "workspace",
    )
    return {**state, "profile_complete": True, "profile_valid": True}


def _configure_edit_classification(touches_goal: bool) -> None:
    configure_user_intent_judge(
        lambda _query: UserIntentJudgement(
            user_intent="edit",
            reason="Test stub.",
            mentions_submitted_plan=False,
            touches_goal_or_constraints=touches_goal,
        )
    )


def test_supervisor_stores_execution_plan_for_edit_when_flag_on(
    initial_state: OrchestrationState, monkeypatch: pytest.MonkeyPatch
) -> None:
    _configure_generate_classification_stubs()
    _configure_edit_classification(touches_goal=False)
    monkeypatch.setenv("RUN_EXECUTION_PLAN_ENABLED", "true")
    monkeypatch.setenv("EDIT_WORKFLOW_V2_ENABLED", "true")
    get_settings.cache_clear()

    result = supervisor_node(dict(initial_state))

    assert result.get("route_decision") != "REFUSED"
    assert result["execution_plan"]["workflow"] == "EditWorkflow"
    assert result["execution_plan"]["fitness_mode"] == "edit"
    assert result["execution_plan"]["verification_strategy"] == "EDIT_REVIEW"


def test_supervisor_uses_with_replan_workflow_when_goal_touched(
    initial_state: OrchestrationState, monkeypatch: pytest.MonkeyPatch
) -> None:
    _configure_generate_classification_stubs()
    _configure_edit_classification(touches_goal=True)
    monkeypatch.setenv("RUN_EXECUTION_PLAN_ENABLED", "true")
    monkeypatch.setenv("EDIT_WORKFLOW_V2_ENABLED", "true")
    get_settings.cache_clear()

    result = supervisor_node(dict(initial_state))

    assert result["execution_plan"]["workflow"] == "EditWithReplanWorkflow"
    assert result["execution_plan"]["ordered_domains"] == ["planning", "fitness", "verify"]


def test_supervisor_edit_falls_back_silently_when_flag_off(
    initial_state: OrchestrationState, monkeypatch: pytest.MonkeyPatch
) -> None:
    """No REFUSED for edit when the flag is off -- unlike verify, edit already works via
    legacy inference, so silent fallback (not an error message) is correct."""
    _configure_generate_classification_stubs()
    _configure_edit_classification(touches_goal=False)
    monkeypatch.setenv("RUN_EXECUTION_PLAN_ENABLED", "true")
    monkeypatch.setenv("EDIT_WORKFLOW_V2_ENABLED", "false")
    get_settings.cache_clear()

    result = supervisor_node(dict(initial_state))

    assert "execution_plan" not in result
    assert result.get("route_decision") != "REFUSED"


# --- verification/strategies.py: EDIT_REVIEW carry-forward ------------------------------


def _write_prior_report(workspace_path: str, report: dict) -> None:
    vfs = VFS.for_run(Path(workspace_path))
    vfs.write("verify/verification_v1.json", json.dumps(report))


def test_edit_review_carries_forward_citation_and_faithfulness(tmp_path: Path) -> None:
    from core.subgraphs.verification.strategies import resolve_strategy

    workspace_path = str(tmp_path / "workspace")
    prior_report = {
        "citation": {"passed": True, "issues": []},
        "consistency": {"passed": True, "issues": []},
        "safety": {"passed": True, "issues": []},
        "ragas": {"pass_fail": True, "faithfulness_score": 0.95},
        "passed": True,
    }
    _write_prior_report(workspace_path, prior_report)

    strategy = resolve_strategy("EDIT_REVIEW", workspace_path)
    node_names = [step.node_name for step in strategy]
    assert node_names == [
        "consistency_check",
        "safety_check",
        "citation_carry_forward",
        "faithfulness_carry_forward",
    ]

    carried_citation = strategy[2].run({"workspace_path": workspace_path})
    assert carried_citation == prior_report["citation"]
    carried_ragas = strategy[3].run({"workspace_path": workspace_path})
    assert carried_ragas == prior_report["ragas"]


def test_edit_review_falls_back_to_full_when_no_prior_report(tmp_path: Path) -> None:
    """Design review F8: no prior report to carry forward from (first-ever edit) --
    EDIT_REVIEW degrades to running FULL's complete validator list once."""
    from core.subgraphs.verification.strategies import VERIFICATION_STRATEGIES, resolve_strategy

    workspace_path = str(tmp_path / "workspace-no-prior")
    strategy = resolve_strategy("EDIT_REVIEW", workspace_path)
    assert strategy == VERIFICATION_STRATEGIES["FULL"]


def test_edit_review_without_workspace_path_uses_carry_forward_shape() -> None:
    """Callers that don't need the F8 fallback (e.g. persist_trigger_data) get the
    carry-forward shape directly."""
    from core.subgraphs.verification.strategies import resolve_strategy

    strategy = resolve_strategy("EDIT_REVIEW")
    assert [step.node_name for step in strategy][:2] == ["consistency_check", "safety_check"]


def test_persist_trigger_recognizes_edit_review_faithfulness_via_report_key() -> None:
    """Regression guard: FAITHFULNESS-by-identity would have missed EDIT_REVIEW's
    carry-forward step (a different ValidatorStep instance with the same report_key)."""
    from core.persist.utils import persist_trigger_data

    result = persist_trigger_data(
        verification_passed=True,
        faithfulness_score=None,
        approval_status="pending",
        verification_strategy="EDIT_REVIEW",
    )
    assert "faithfulness_below_threshold" in result["persist_blocked_reasons"]
