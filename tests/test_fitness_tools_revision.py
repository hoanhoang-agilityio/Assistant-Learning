"""select_template/populate_template (core.capabilities.fitness.tools) used to hardcode
fitness_mode="generate"/days_per_week_explicit=False/no revision_feedback, which made
resolve_workout_template's already-correct edit-mode logic (see test_fitness_blueprint.py)
unreachable in production -- every revision silently regenerated from scratch, ignoring
the user's actual request text. These tests cover the wiring fix at the tools.py layer
that the executor (_run_build_plan) calls into."""

import json
from pathlib import Path
from unittest.mock import patch

from core.adapters.vfs import VFS
from core.capabilities.fitness import tools as fitness_tools
from core.capabilities.fitness.schema import EditOperation
from core.orchestration.graph.run import create_initial_state
from core.shared.planning.utils import persist_revision_feedback
from tests.helpers.fitness import default_structured_workout


def _seed_prior_workout(workspace_path: str, profile: dict, constraints: dict) -> None:
    workout = default_structured_workout(profile, constraints).model_dump()
    VFS.for_run(Path(workspace_path)).write("fitness/workout.json", json.dumps(workout))


def test_select_template_skips_deterministic_shortcut_when_days_per_week_explicit(
    workspace_root: Path, complete_profile: dict, monkeypatch
) -> None:
    """A revision that explicitly names a new training frequency must reach the LLM
    edit path (so the workout structure actually changes), not the deterministic
    UPDATE_MACROS shortcut, which never changes day count."""
    state = create_initial_state(
        run_id="select-template-explicit-days",
        thread_id="select-template-explicit-days-thread",
        query="change to 5 day training per week",
        user_profile=complete_profile,
        constraints={"days_per_week": 3, "equipment": "gym"},
        workspace_root=workspace_root,
    )
    workspace = state["workspace_path"]
    _seed_prior_workout(workspace, complete_profile, {"days_per_week": 3, "equipment": "gym"})
    persist_revision_feedback(workspace, "change to 5 day training per week")
    monkeypatch.setattr(
        "core.capabilities.fitness.template_registry.classify_edit_operation",
        lambda revision_feedback, current_exercise_names: EditOperation(operation="UPDATE_MACROS"),
    )

    result = fitness_tools.select_template(workspace, days_per_week_explicit=True)

    assert result["structured_workout"] is None
    assert result["workout_source"] == "llm_required"
    assert result["edit_operation"]["operation"] == "UPDATE_MACROS"
    assert result["previous_workout"] is not None


def test_select_template_takes_deterministic_shortcut_when_days_per_week_not_explicit(
    workspace_root: Path, complete_profile: dict, monkeypatch
) -> None:
    state = create_initial_state(
        run_id="select-template-macro-only",
        thread_id="select-template-macro-only-thread",
        query="give me more protein",
        user_profile=complete_profile,
        constraints={"days_per_week": 3, "equipment": "gym"},
        workspace_root=workspace_root,
    )
    workspace = state["workspace_path"]
    _seed_prior_workout(workspace, complete_profile, {"days_per_week": 3, "equipment": "gym"})
    persist_revision_feedback(workspace, "give me more protein")
    monkeypatch.setattr(
        "core.capabilities.fitness.template_registry.classify_edit_operation",
        lambda revision_feedback, current_exercise_names: EditOperation(operation="UPDATE_MACROS"),
    )

    result = fitness_tools.select_template(workspace, days_per_week_explicit=False)

    assert result["workout_source"] == "deterministic_edit"
    assert result["structured_workout"] is not None


def test_select_template_ignores_stale_revision_feedback_on_first_build(
    workspace_root: Path, complete_profile: dict
) -> None:
    """No revision_feedback on disk and no prior workout -- a first-time build must
    behave exactly as plain generation (fitness_mode=None auto-detects, doesn't force
    edit mode when there's nothing to edit)."""
    state = create_initial_state(
        run_id="select-template-first-build",
        thread_id="select-template-first-build-thread",
        query="Build me a plan",
        user_profile=complete_profile,
        constraints={"days_per_week": 3, "equipment": "gym"},
        workspace_root=workspace_root,
    )

    result = fitness_tools.select_template(state["workspace_path"])

    assert result["edit_operation"] is None
    assert result["previous_workout"] is None


def test_populate_template_uses_edit_mode_and_threads_revision_feedback(
    workspace_root: Path, complete_profile: dict
) -> None:
    state = create_initial_state(
        run_id="populate-template-edit",
        thread_id="populate-template-edit-thread",
        query="change to 5 day training per week",
        user_profile=complete_profile,
        constraints={"days_per_week": 3, "equipment": "gym"},
        workspace_root=workspace_root,
    )
    workspace = state["workspace_path"]
    prior = default_structured_workout(complete_profile, {"days_per_week": 3}).model_dump()
    persist_revision_feedback(workspace, "change to 5 day training per week")

    with patch("core.capabilities.fitness.tools.generate_structured_workout") as mock_generate:
        mock_generate.return_value = default_structured_workout(
            complete_profile, {"days_per_week": 5}
        )
        fitness_tools.populate_template(
            workspace,
            previous_workout=prior,
            edit_operation={"operation": "ADD_DAY"},
        )

    _, kwargs = mock_generate.call_args
    assert kwargs["mode"] == "edit"
    assert kwargs["previous_workout"] == prior
    assert kwargs["edit_operation"] == EditOperation(operation="ADD_DAY")
    assert kwargs["revision_feedback"] == "change to 5 day training per week"


def test_populate_template_uses_generate_mode_without_previous_workout(
    workspace_root: Path, complete_profile: dict
) -> None:
    state = create_initial_state(
        run_id="populate-template-generate",
        thread_id="populate-template-generate-thread",
        query="Build me a plan",
        user_profile=complete_profile,
        constraints={"days_per_week": 3, "equipment": "gym"},
        workspace_root=workspace_root,
    )
    workspace = state["workspace_path"]

    with patch("core.capabilities.fitness.tools.generate_structured_workout") as mock_generate:
        mock_generate.return_value = default_structured_workout(
            complete_profile, {"days_per_week": 3}
        )
        fitness_tools.populate_template(workspace)

    _, kwargs = mock_generate.call_args
    assert kwargs["mode"] == "generate"
    assert kwargs["previous_workout"] is None
    assert kwargs["edit_operation"] is None
