"""Workout template fingerprinting and reuse helpers.

Template storage lives behind the Fitness MCP Server (core.mcp.fitness_client) --
this module owns fingerprinting/reuse decision logic only.
"""

import hashlib
import json
import logging
from pathlib import Path
from typing import Any

from core.capabilities.fitness.blueprint import PlanBlueprint, session_duration_bucket_from_profile
from core.capabilities.fitness.edit_classifier import classify_edit_operation
from core.capabilities.fitness.schema import StructuredWorkout
from core.capabilities.fitness.utils import (
    apply_deterministic_edit,
    flatten_exercise_names,
    is_cacheable_workout,
)
from core.mcp.fitness_client import get_fitness_client
from core.shared.planning.utils import load_revision_feedback
from core.vfs import VFS

logger = logging.getLogger(__name__)


def workout_template_fingerprint(
    *,
    template_family: str,
    days_per_week: int,
    equipment: str,
    session_duration_bucket: str,
    experience_level: str = "intermediate",
) -> str:
    payload = {
        "template_family": template_family,
        "days_per_week": days_per_week,
        "equipment": equipment,
        "session_duration_bucket": session_duration_bucket,
        "experience_level": experience_level,
    }
    digest = hashlib.sha256(json.dumps(payload, sort_keys=True).encode("utf-8")).hexdigest()
    return digest[:16]


def build_template_fingerprint(
    profile: dict[str, Any],
    constraints: dict[str, Any],
    blueprint: PlanBlueprint,
) -> str:
    days_per_week = int(profile.get("days_per_week") or constraints.get("days_per_week") or 3)
    equipment = str(constraints.get("equipment") or profile.get("equipment") or "gym")
    return workout_template_fingerprint(
        template_family=blueprint.template_family,
        days_per_week=days_per_week,
        equipment=equipment,
        session_duration_bucket=session_duration_bucket_from_profile(profile, constraints),
    )


def load_prior_workout(workspace_path: str) -> dict[str, Any] | None:
    vfs = VFS.for_run(Path(workspace_path))
    if not vfs.exists("fitness/workout.json"):
        return None
    return json.loads(vfs.read("fitness/workout.json"))


def should_reuse_prior_workout(
    *,
    workspace_path: str,
    fingerprint: str,
    planner_feedback: list[str],
    verification_feedback: str | None,
    is_verification_rerun: bool,
) -> bool:
    if not is_verification_rerun:
        return False
    if planner_feedback or verification_feedback:
        return False
    vfs = VFS.for_run(Path(workspace_path))
    if not vfs.exists("fitness/template_fingerprint.json"):
        return False
    stored = json.loads(vfs.read("fitness/template_fingerprint.json"))
    return (
        stored.get("fingerprint") == fingerprint and load_prior_workout(workspace_path) is not None
    )


def resolve_workout_template(
    *,
    workspace_path: str,
    profile: dict[str, Any],
    constraints: dict[str, Any],
    blueprint: PlanBlueprint,
    planner_feedback: list[str],
    verification_feedback: str | None,
    is_verification_rerun: bool,
    days_per_week_explicit: bool = False,
    fitness_mode: str | None = None,
) -> dict[str, Any]:
    fingerprint = build_template_fingerprint(profile, constraints, blueprint)
    if planner_feedback:
        return {
            "structured_workout": None,
            "template_fingerprint": fingerprint,
            "workout_source": "llm_required",
            "reused_workout": False,
        }

    revision_feedback = load_revision_feedback(workspace_path)
    is_edit_mode = fitness_mode == "edit" if fitness_mode is not None else bool(revision_feedback)
    if is_edit_mode:
        prior_workout = load_prior_workout(workspace_path)
        if prior_workout is None:
            # No existing plan to edit (e.g. revision feedback landed before the
            # first-ever generation) -- fall back to a normal, unscoped generation.
            return {
                "structured_workout": None,
                "template_fingerprint": fingerprint,
                "workout_source": "llm_required",
                "reused_workout": False,
            }

        operation = classify_edit_operation(
            revision_feedback, flatten_exercise_names(prior_workout)
        )

        # The deterministic shortcut only ever touches macros or a single exercise --
        # it never changes day count. When this revision explicitly changes training
        # frequency, the workout structure necessarily changes too, so a deterministic
        # edit would always fail the day-count safety check and waste a retry. Skip it
        # and let the planner generate the correct structure in one pass instead.
        if not days_per_week_explicit and operation.operation in (
            "UPDATE_MACROS",
            "REPLACE_EXERCISE",
        ):
            deterministic_result = apply_deterministic_edit(operation, prior_workout)
            if deterministic_result is not None:
                return {
                    "structured_workout": deterministic_result,
                    "template_fingerprint": fingerprint,
                    "workout_source": "deterministic_edit",
                    "reused_workout": True,
                }
            # Ambiguous/no-match deterministic attempt (e.g. REPLACE_EXERCISE with
            # zero or multiple matches) falls through to edit-mode generation below,
            # same as ADD_DAY/REMOVE_DAY/OTHER.

        return {
            "structured_workout": None,
            "template_fingerprint": fingerprint,
            "workout_source": "llm_required",
            "reused_workout": False,
            "edit_operation": operation.model_dump(),
            "previous_workout": prior_workout,
        }

    if should_reuse_prior_workout(
        workspace_path=workspace_path,
        fingerprint=fingerprint,
        planner_feedback=planner_feedback,
        verification_feedback=verification_feedback,
        is_verification_rerun=is_verification_rerun,
    ):
        return {
            "structured_workout": load_prior_workout(workspace_path),
            "template_fingerprint": fingerprint,
            "workout_source": "run_reuse",
            "reused_workout": True,
        }

    cached = None
    client = get_fitness_client()
    if client is not None:
        try:
            cached = client.search_training_template(fingerprint).get("workout")
        except Exception:
            logger.warning(
                "Fitness MCP template lookup failed; treating as cache miss", exc_info=True
            )
    if cached is not None and is_cacheable_workout(cached):
        return {
            "structured_workout": cached,
            "template_fingerprint": fingerprint,
            "workout_source": "registry",
            "reused_workout": True,
        }

    return {
        "structured_workout": None,
        "template_fingerprint": fingerprint,
        "workout_source": "llm_required",
        "reused_workout": False,
    }


def store_workout_template(
    fingerprint: str,
    workout: dict[str, Any],
    *,
    source: str,
) -> None:
    """Persist an LLM-generated workout for cross-run reuse."""
    if source != "llm":
        return
    if not is_cacheable_workout(workout):
        return
    client = get_fitness_client()
    if client is None:
        return
    try:
        client.store_training_template(fingerprint, workout)
    except Exception:
        logger.warning("Fitness MCP template store failed; will regenerate next run", exc_info=True)


def adapt_workout_to_blueprint(
    structured_workout: dict[str, Any],
    blueprint: PlanBlueprint,
) -> dict[str, Any]:
    if not blueprint.phases:
        return structured_workout
    workout = StructuredWorkout.model_validate(structured_workout)
    volume_modifier = blueprint.phases[0].volume_modifier
    adapted_days = []
    for day in workout.days:
        adapted_exercises = []
        for exercise in day.exercises:
            scaled_sets = max(1, min(10, round(exercise.sets * volume_modifier)))
            adapted_exercises.append(exercise.model_copy(update={"sets": scaled_sets}))
        adapted_days.append(day.model_copy(update={"exercises": adapted_exercises}))
    weekly_sets = sum(exercise.sets for day in adapted_days for exercise in day.exercises)
    notes = list(workout.notes)
    if blueprint.horizon_weeks:
        notes.append(f"Blueprint horizon: {blueprint.horizon_weeks} weeks.")
    if blueprint.weekly_rate_kg is not None:
        notes.append(f"Target weekly rate: {blueprint.weekly_rate_kg} kg.")
    adapted = workout.model_copy(
        update={
            "days": adapted_days,
            "weekly_sets": weekly_sets,
            "notes": notes,
        }
    )
    return adapted.model_dump()
