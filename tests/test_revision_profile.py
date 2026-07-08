from core.graph.run import create_initial_state
from core.profile.extraction import configure_profile_extractor
from core.profile.schema import Constraints, ExtractedProfile
from core.subgraphs.fitness.schema import StructuredWorkout, WorkoutDay, WorkoutExercise
from core.subgraphs.fitness.utils import (
    ensure_training_day_count,
)
from core.subgraphs.planning.graph import build_planning_subgraph
from core.subgraphs.planning.state import PlanningState
from core.subgraphs.planning.utils import apply_revision_overrides, build_profile


def test_apply_revision_overrides_updates_days_per_week() -> None:
    configure_profile_extractor(
        lambda _query: ExtractedProfile(constraints=Constraints(days_per_week=5))
    )
    profile = {
        "age": 27,
        "sex": "male",
        "height_cm": 171,
        "current_weight_kg": 73.0,
        "target_weight_kg": 70.0,
        "goal": "fat_loss",
        "days_per_week": 4,
        "activity_level": "gym_4x_week",
        "equipment": "gym",
    }
    updated = apply_revision_overrides(profile, "i want to change to train 5 days per week")
    assert updated["days_per_week"] == 5
    assert updated["activity_level"] == "gym_5x_week"
    assert updated["age"] == 27
    assert updated["goal"] == "fat_loss"


def test_build_profile_applies_revision_without_reasking_profile(complete_profile: dict) -> None:
    configure_profile_extractor(
        lambda query: (
            ExtractedProfile(constraints=Constraints(days_per_week=5))
            if "5 days" in query.lower()
            else ExtractedProfile()
        )
    )
    profile = build_profile(
        query="I want a 4-day training plan to lose weight.",
        user_profile=complete_profile,
        constraints={"days_per_week": 4, "equipment": "gym"},
        revision_feedback="i want to change to train 5 days per week",
    )
    assert profile["days_per_week"] == 5
    assert profile["activity_level"] == "gym_5x_week"


def test_replan_subgraph_updates_days_per_week_from_revision_feedback(
    complete_profile: dict,
    workspace_root,
) -> None:
    configure_profile_extractor(
        lambda query: (
            ExtractedProfile(
                constraints=Constraints(days_per_week=5),
            )
            if "5 days" in query.lower()
            else ExtractedProfile()
        )
    )
    initial = create_initial_state(
        run_id="revision-run",
        thread_id="revision-thread",
        query="I want a 4-day training plan to lose weight.",
        user_profile=complete_profile,
        workspace_root=workspace_root,
    )
    state: PlanningState = {
        "query": initial["query"],
        "user_profile": {
            **complete_profile,
            "days_per_week": 4,
            "activity_level": "gym_4x_week",
        },
        "constraints": {"days_per_week": 4, "equipment": "gym"},
        "request_type": "fat_loss",
        "workspace_path": initial["workspace_path"],
        "route_decision": "REPLAN",
        "revision_feedback": "i want to change to train 5 days per week",
        "profile": {},
        "missing_fields": [],
        "requires_hitl": False,
        "approved_tools": [],
        "used_llm_extraction": False,
        "requires_tool_approval": False,
        "reused_execution_plan": False,
    }
    result = build_planning_subgraph().invoke(state)
    assert result["profile"]["days_per_week"] == 5
    assert result["profile"]["activity_level"] == "gym_5x_week"


def test_apply_revision_overrides_parses_days_from_natural_language() -> None:
    profile = {
        "age": 27,
        "sex": "male",
        "height_cm": 171,
        "current_weight_kg": 73.0,
        "target_weight_kg": 70.0,
        "goal": "fat_loss",
        "days_per_week": 4,
        "activity_level": "gym_4x_week",
        "equipment": "gym",
    }
    configure_profile_extractor(lambda _query: ExtractedProfile())
    updated = apply_revision_overrides(profile, "i want to train 3 days per week")
    assert updated["days_per_week"] == 3
    assert updated["activity_level"] == "gym_3x_week"


def test_ensure_training_day_count_fills_missing_days() -> None:
    workout = StructuredWorkout(
        split="full body",
        goal="fat_loss",
        days=[
            WorkoutDay(
                name="Day 1",
                focus="full body",
                exercises=[WorkoutExercise(name="Squat", sets=3, reps="8-10")],
            )
        ],
        weekly_sets=3,
        progression="Add load weekly.",
        substitutions=[],
        notes=[],
        evidence_applied=[],
    )
    repaired = ensure_training_day_count(
        workout,
        {"days_per_week": 3, "equipment": "gym"},
        {"goal": "fat_loss", "days_per_week": 3},
    )
    assert len(repaired.days) == 3
