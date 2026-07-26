"""Tests for fitness blueprint and template reuse."""

import json
from pathlib import Path

from core.profile.goal_spec import derive_goal_spec
from core.subgraphs.fitness.blueprint import build_plan_blueprint
from core.subgraphs.fitness.schema import EditOperation
from core.subgraphs.fitness.template_registry import (
    TemplateRegistry,
    adapt_workout_to_blueprint,
    build_template_fingerprint,
    resolve_workout_template,
    store_workout_template,
)
from core.subgraphs.fitness.utils import BENCHMARK_WORKOUT_NOTE, build_default_structured_workout
from core.subgraphs.planning.utils import persist_revision_feedback
from core.vfs import VFS
from tests.helpers.fitness import default_structured_workout


def test_build_plan_blueprint_includes_horizon() -> None:
    profile = {
        "goal": "muscle_gain",
        "current_weight_kg": 73.0,
        "target_weight_kg": 75.0,
        "horizon_weeks": 52,
        "days_per_week": 4,
    }
    constraints = {"equipment": "gym"}
    blueprint = build_plan_blueprint(profile, constraints, derive_goal_spec(profile))
    assert blueprint.horizon_weeks == 52
    assert blueprint.template_family == "muscle_gain_4day_gym"
    assert blueprint.phases


def test_template_registry_reuse_by_fingerprint() -> None:
    profile = {"goal": "muscle_gain", "days_per_week": 3, "equipment": "gym"}
    constraints = {"equipment": "gym", "days_per_week": 3}
    blueprint = build_plan_blueprint(profile, constraints, derive_goal_spec(profile))
    fingerprint = build_template_fingerprint(profile, constraints, blueprint)
    workout = default_structured_workout(profile, constraints).model_dump()
    workout["notes"] = ["Cacheable LLM workout for registry reuse test."]
    registry = TemplateRegistry()
    registry.clear()
    registry.put(fingerprint, workout)
    resolution = resolve_workout_template(
        workspace_path="/tmp/unused",
        profile=profile,
        constraints=constraints,
        blueprint=blueprint,
        planner_feedback=[],
        verification_feedback=None,
        is_verification_rerun=False,
    )
    assert resolution["workout_source"] == "registry"
    assert resolution["structured_workout"] is not None


def test_template_registry_skips_cache_when_revision_feedback_present(tmp_path) -> None:
    profile = {"goal": "muscle_gain", "days_per_week": 3, "equipment": "gym"}
    constraints = {"equipment": "gym", "days_per_week": 3}
    blueprint = build_plan_blueprint(profile, constraints, derive_goal_spec(profile))
    fingerprint = build_template_fingerprint(profile, constraints, blueprint)
    workout = default_structured_workout(profile, constraints).model_dump()
    workout["notes"] = ["Cacheable LLM workout for registry reuse test."]
    registry = TemplateRegistry()
    registry.clear()
    registry.put(fingerprint, workout)
    workspace_path = str(tmp_path / "revision-workspace")
    persist_revision_feedback(workspace_path, "train 5 days per week")
    resolution = resolve_workout_template(
        workspace_path=workspace_path,
        profile=profile,
        constraints=constraints,
        blueprint=blueprint,
        planner_feedback=[],
        verification_feedback=None,
        is_verification_rerun=False,
    )
    assert resolution["workout_source"] == "llm_required"
    assert resolution["structured_workout"] is None


def _seed_prior_workout(workspace_path: str, profile: dict, constraints: dict) -> dict:
    workout = default_structured_workout(profile, constraints).model_dump()
    VFS.for_run(Path(workspace_path)).write("fitness/workout.json", json.dumps(workout))
    return workout


def test_deterministic_edit_applies_when_days_per_week_not_explicit(tmp_path, monkeypatch) -> None:
    """Baseline: a macro-only edit still takes the deterministic shortcut untouched."""
    profile = {"goal": "muscle_gain", "days_per_week": 4, "equipment": "gym"}
    constraints = {"equipment": "gym", "days_per_week": 4}
    blueprint = build_plan_blueprint(profile, constraints, derive_goal_spec(profile))
    workspace_path = str(tmp_path / "edit-workspace")
    _seed_prior_workout(workspace_path, profile, constraints)
    persist_revision_feedback(workspace_path, "give me more protein")
    monkeypatch.setattr(
        "core.subgraphs.fitness.template_registry.classify_edit_operation",
        lambda revision_feedback, current_exercise_names: EditOperation(operation="UPDATE_MACROS"),
    )

    resolution = resolve_workout_template(
        workspace_path=workspace_path,
        profile=profile,
        constraints=constraints,
        blueprint=blueprint,
        planner_feedback=[],
        verification_feedback=None,
        is_verification_rerun=False,
        days_per_week_explicit=False,
    )

    assert resolution["workout_source"] == "deterministic_edit"
    assert resolution["reused_workout"] is True


def test_deterministic_edit_skipped_when_days_per_week_explicit(tmp_path, monkeypatch) -> None:
    """A macro edit that also explicitly changes frequency must not take the shortcut --
    it would preserve the old day count and guarantee a safety-check failure/retry."""
    profile = {"goal": "muscle_gain", "days_per_week": 3, "equipment": "gym"}
    constraints = {"equipment": "gym", "days_per_week": 3}
    blueprint = build_plan_blueprint(profile, constraints, derive_goal_spec(profile))
    workspace_path = str(tmp_path / "edit-workspace")
    old_profile = {**profile, "days_per_week": 4}
    old_constraints = {**constraints, "days_per_week": 4}
    _seed_prior_workout(workspace_path, old_profile, old_constraints)
    persist_revision_feedback(workspace_path, "reduce training to 3 days and increase protein")
    monkeypatch.setattr(
        "core.subgraphs.fitness.template_registry.classify_edit_operation",
        lambda revision_feedback, current_exercise_names: EditOperation(operation="UPDATE_MACROS"),
    )

    resolution = resolve_workout_template(
        workspace_path=workspace_path,
        profile=profile,
        constraints=constraints,
        blueprint=blueprint,
        planner_feedback=[],
        verification_feedback=None,
        is_verification_rerun=False,
        days_per_week_explicit=True,
    )

    assert resolution["workout_source"] == "llm_required"
    assert resolution["structured_workout"] is None
    assert resolution["edit_operation"]["operation"] == "UPDATE_MACROS"
    assert resolution["previous_workout"] is not None


def test_deterministic_replace_exercise_skipped_when_days_per_week_explicit(
    tmp_path, monkeypatch
) -> None:
    """Same skip behavior applies to REPLACE_EXERCISE-classified compound requests."""
    profile = {"goal": "muscle_gain", "days_per_week": 5, "equipment": "gym"}
    constraints = {"equipment": "gym", "days_per_week": 5}
    blueprint = build_plan_blueprint(profile, constraints, derive_goal_spec(profile))
    workspace_path = str(tmp_path / "edit-workspace")
    old_profile = {**profile, "days_per_week": 4}
    old_constraints = {**constraints, "days_per_week": 4}
    _seed_prior_workout(workspace_path, old_profile, old_constraints)
    persist_revision_feedback(
        workspace_path, "swap bench press for dumbbell press and train 5 days instead"
    )
    monkeypatch.setattr(
        "core.subgraphs.fitness.template_registry.classify_edit_operation",
        lambda revision_feedback, current_exercise_names: EditOperation(
            operation="REPLACE_EXERCISE",
            target_exercise="bench press",
            replacement_exercise="dumbbell press",
        ),
    )

    resolution = resolve_workout_template(
        workspace_path=workspace_path,
        profile=profile,
        constraints=constraints,
        blueprint=blueprint,
        planner_feedback=[],
        verification_feedback=None,
        is_verification_rerun=False,
        days_per_week_explicit=True,
    )

    assert resolution["workout_source"] == "llm_required"
    assert resolution["structured_workout"] is None
    assert resolution["edit_operation"]["operation"] == "REPLACE_EXERCISE"


def test_adapt_workout_scales_volume_from_blueprint() -> None:
    profile = {"goal": "fat_loss", "days_per_week": 3}
    constraints = {"equipment": "gym", "days_per_week": 3}
    blueprint = build_plan_blueprint(profile, constraints, derive_goal_spec(profile))
    workout = default_structured_workout(profile, constraints).model_dump()
    adapted = adapt_workout_to_blueprint(workout, blueprint)
    assert adapted["weekly_sets"] <= workout["weekly_sets"]


def test_default_workout_rotates_push_pull_legs() -> None:
    workout = build_default_structured_workout(
        {"goal": "muscle_gain"},
        {"days_per_week": 3, "equipment": "gym"},
    )
    focuses = [day.focus for day in workout.days]
    assert focuses == ["push", "pull", "legs"]
    exercise_names_by_day = [[exercise.name for exercise in day.exercises] for day in workout.days]
    assert exercise_names_by_day[0] != exercise_names_by_day[1]
    assert exercise_names_by_day[1] != exercise_names_by_day[2]


def test_store_workout_template_skips_benchmark_and_non_llm_sources() -> None:
    profile = {"goal": "muscle_gain", "days_per_week": 3}
    constraints = {"equipment": "gym", "days_per_week": 3}
    blueprint = build_plan_blueprint(profile, constraints, derive_goal_spec(profile))
    fingerprint = build_template_fingerprint(profile, constraints, blueprint)
    benchmark_workout = default_structured_workout(profile, constraints).model_dump()
    registry = TemplateRegistry()
    registry.clear()

    store_workout_template(fingerprint, benchmark_workout, source="llm")
    assert registry.get(fingerprint) is None

    cacheable_workout = {
        **benchmark_workout,
        "notes": ["LLM generated workout."],
    }
    store_workout_template(fingerprint, cacheable_workout, source="registry")
    assert registry.get(fingerprint) is None

    store_workout_template(fingerprint, cacheable_workout, source="llm")
    cached = registry.get(fingerprint)
    assert cached is not None
    assert BENCHMARK_WORKOUT_NOTE not in str(cached.get("notes"))
