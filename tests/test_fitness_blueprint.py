"""Tests for fitness blueprint and template reuse."""

from core.subgraphs.fitness.blueprint import build_plan_blueprint
from core.subgraphs.fitness.template_registry import (
    TemplateRegistry,
    adapt_workout_to_blueprint,
    build_template_fingerprint,
    resolve_workout_template,
    store_workout_template,
)
from core.subgraphs.fitness.utils import BENCHMARK_WORKOUT_NOTE, build_default_structured_workout
from core.subgraphs.planning.utils import persist_revision_feedback
from tests.helpers.fitness import default_structured_workout


def test_build_plan_blueprint_includes_horizon() -> None:
    profile = {
        "goal": "muscle_gain",
        "current_weight_kg": 73.0,
        "weight_delta_kg": 2.0,
        "horizon_weeks": 52,
        "days_per_week": 4,
    }
    constraints = {"equipment": "gym"}
    blueprint = build_plan_blueprint(profile, constraints)
    assert blueprint.horizon_weeks == 52
    assert blueprint.template_family == "muscle_gain_4day_gym"
    assert blueprint.phases


def test_template_registry_reuse_by_fingerprint() -> None:
    profile = {"goal": "muscle_gain", "days_per_week": 3, "equipment": "gym"}
    constraints = {"equipment": "gym", "days_per_week": 3}
    blueprint = build_plan_blueprint(profile, constraints)
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
    blueprint = build_plan_blueprint(profile, constraints)
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


def test_adapt_workout_scales_volume_from_blueprint() -> None:
    profile = {"goal": "fat_loss", "days_per_week": 3}
    constraints = {"equipment": "gym", "days_per_week": 3}
    blueprint = build_plan_blueprint(profile, constraints)
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
    blueprint = build_plan_blueprint(profile, constraints)
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
