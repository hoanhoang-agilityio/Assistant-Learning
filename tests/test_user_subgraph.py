from pathlib import Path
from typing import Any

from core.graph.run import create_initial_state
from core.shared.profile.extraction import configure_profile_extractor
from core.shared.profile.goal_spec import derive_goal_spec
from core.shared.profile.schema import Constraints, ExtractedProfile, Goal, Profile
from core.subgraphs.user.agent import UserAgent
from core.subgraphs.user.utils import (
    extract_profile,
    load_stored_profile,
    resolve_extraction_query,
    validate_profile_completeness,
)


def _make_state(
    *,
    run_id: str,
    workspace_root: Path,
    query: str,
    user_profile: dict[str, Any],
    revision_feedback: str | None = None,
) -> dict[str, Any]:
    state = dict(
        create_initial_state(
            run_id=run_id,
            thread_id=run_id,
            query=query,
            user_profile=user_profile,
            workspace_root=workspace_root,
        )
    )
    # These tests exercise UserAgent/to_user_state directly, bypassing supervisor_node --
    # so fitness_query (normally set only on an ALLOW scope decision) must be set here too.
    state["fitness_query"] = query
    state["revision_feedback"] = revision_feedback
    return state


def test_complete_profile_skips_form_and_persists(
    workspace_root: Path, complete_profile: dict[str, Any]
) -> None:
    """A query paired with an already-complete, feasible profile needs no form at all."""
    state = _make_state(
        run_id="user-run-1",
        workspace_root=workspace_root,
        query="I want a fat loss plan.",
        user_profile=complete_profile,
    )
    agent = UserAgent()
    result = agent.run(state)

    assert "__interrupt__" not in result
    assert result["profile_complete"] is True
    assert result["profile_valid"] is True
    assert result["waiting_for_user"] is False

    stored = load_stored_profile(result["workspace_path"])
    assert stored["age"] == 30
    assert stored["goal"] == "fat_loss"


def test_missing_fields_pause_at_form_then_resume_completes(workspace_root: Path) -> None:
    """An incomplete profile pauses via interrupt() and resumes via Command(resume=...)."""
    incomplete_profile = {"age": 30, "height_cm": 175}
    state = _make_state(
        run_id="user-run-2",
        workspace_root=workspace_root,
        query="I want to get fit.",
        user_profile=incomplete_profile,
    )
    configure_profile_extractor(lambda _query: ExtractedProfile())

    agent = UserAgent()
    result = agent.run(state)

    assert "__interrupt__" in result
    interrupt_payload = result["__interrupt__"][0].value
    assert interrupt_payload["type"] == "profile_form"
    missing = set(interrupt_payload["missing_fields"])
    assert {"sex", "current_weight_kg", "target_weight_kg"} <= missing

    snapshot = agent.get_state(state)
    assert snapshot.next == ("user",)
    assert snapshot.tasks[0].interrupts

    form_data = {
        "sex": "male",
        "current_weight_kg": 80.0,
        "target_weight_kg": 75.0,
    }
    resumed = agent.resume(state, form_data)

    assert "__interrupt__" not in resumed
    assert resumed["profile_complete"] is True
    assert resumed["profile_valid"] is True
    assert resumed["waiting_for_user"] is False

    stored = load_stored_profile(resumed["workspace_path"])
    assert stored["sex"] == "male"
    assert stored["current_weight_kg"] == 80.0


def test_still_incomplete_resubmission_loops_back_to_form(workspace_root: Path) -> None:
    """A partial resubmission re-enters the form with fresh feedback instead of proceeding."""
    incomplete_profile = {"age": 28}
    state = _make_state(
        run_id="user-run-3",
        workspace_root=workspace_root,
        query="I want to train.",
        user_profile=incomplete_profile,
    )
    configure_profile_extractor(lambda _query: ExtractedProfile())

    agent = UserAgent()
    first = agent.run(state)
    assert "__interrupt__" in first
    first_missing = set(first["__interrupt__"][0].value["missing_fields"])
    assert "sex" in first_missing

    # Submit only some of the missing fields -- still incomplete.
    second = agent.resume(state, {"sex": "female", "height_cm": 165})
    assert "__interrupt__" in second, "still-incomplete resubmission must loop back to the form"
    second_missing = set(second["__interrupt__"][0].value["missing_fields"])
    assert "current_weight_kg" in second_missing
    assert "sex" not in second_missing

    # Complete the remaining fields.
    final = agent.resume(
        state,
        {"current_weight_kg": 60.0, "target_weight_kg": 55.0},
    )
    assert "__interrupt__" not in final
    assert final["profile_complete"] is True
    assert final["profile_valid"] is True


def test_irrelevant_revision_feedback_does_not_reopen_form(
    workspace_root: Path, complete_profile: dict[str, Any]
) -> None:
    """Revision text with no profile content leaves an already-valid profile untouched."""
    state = _make_state(
        run_id="user-run-4a",
        workspace_root=workspace_root,
        query="I want a fat loss plan.",
        user_profile=complete_profile,
        revision_feedback="Please make Tuesday's workout harder.",
    )
    configure_profile_extractor(lambda _query: ExtractedProfile())

    agent = UserAgent()
    result = agent.run(state)

    assert "__interrupt__" not in result
    assert result["profile_complete"] is True
    assert result["profile_valid"] is True


def test_revision_feedback_with_day_count_sets_explicit_flag(
    workspace_root: Path, complete_profile: dict[str, Any]
) -> None:
    """Revision text naming a training-frequency target flags days_per_week_explicit."""
    state = _make_state(
        run_id="user-run-4c",
        workspace_root=workspace_root,
        query="I want a fat loss plan.",
        user_profile=complete_profile,
        revision_feedback="change timeline to 10 weeks and train 5 days per week",
    )
    configure_profile_extractor(lambda _query: ExtractedProfile(goal=Goal(horizon_weeks=10)))

    agent = UserAgent()
    result = agent.run(state)

    assert "__interrupt__" not in result
    assert result["days_per_week_explicit"] is True

    stored = load_stored_profile(result["workspace_path"])
    assert stored["horizon_weeks"] == 10
    assert stored["days_per_week"] == 5


def test_irrelevant_revision_feedback_clears_explicit_flag(
    workspace_root: Path, complete_profile: dict[str, Any]
) -> None:
    """Revision text with no day-count content must not carry a stale explicit flag."""
    state = _make_state(
        run_id="user-run-4d",
        workspace_root=workspace_root,
        query="I want a fat loss plan.",
        user_profile=complete_profile,
        revision_feedback="Please make Tuesday's workout harder.",
    )
    configure_profile_extractor(lambda _query: ExtractedProfile())

    agent = UserAgent()
    result = agent.run(state)

    assert "__interrupt__" not in result
    assert result["days_per_week_explicit"] is False


def test_profile_relevant_revision_feedback_reopens_form(
    workspace_root: Path, complete_profile: dict[str, Any]
) -> None:
    """Revision text that changes the goal without an updated target creates a real conflict."""
    state = _make_state(
        run_id="user-run-4b",
        workspace_root=workspace_root,
        query="I want a fat loss plan.",
        user_profile=complete_profile,
        revision_feedback="Actually I want to switch my goal to muscle gain instead.",
    )
    # complete_profile has target_weight_kg (75) < current_weight_kg (85), i.e. a fat-loss
    # direction; switching only the goal to muscle_gain without updating the target creates a
    # goal_direction_conflict, which must reopen the form even though no field is "missing".
    configure_profile_extractor(lambda _query: ExtractedProfile(goal=Goal(goal="muscle_gain")))

    agent = UserAgent()
    result = agent.run(state)

    assert "__interrupt__" in result
    payload = result["__interrupt__"][0].value
    assert any("goal_direction_conflict" in issue for issue in payload["feasibility_issues"])


# --- Core-function unit tests (relocated from tests/test_planning_subgraph.py, which tested
# these as planning.tools @tool wrappers before extraction/validation moved to this subgraph) ---


def test_resolve_extraction_query_uses_latest_hitl_message(complete_profile: dict) -> None:
    accumulated_query = (
        "I want to lose weight.\nMale, 30 years old, 175 cm, 85 kg. Gym 3x/week. Goal: 75 kg"
    )
    assert resolve_extraction_query(accumulated_query, complete_profile) == (
        "Male, 30 years old, 175 cm, 85 kg. Gym 3x/week. Goal: 75 kg"
    )


def test_resolve_extraction_query_keeps_full_query_without_existing_profile() -> None:
    query = "I want to lose weight.\nMore details here."
    assert resolve_extraction_query(query, {}) == query


def test_extract_profile_merges_query_and_profile() -> None:
    configure_profile_extractor(
        lambda _query: ExtractedProfile(
            profile=Profile(
                sex="male",
                age=30,
                height_cm=175,
                current_weight_kg=85,
            ),
            goal=Goal(goal="fat_loss", target_weight_kg=75),
            constraints=Constraints(days_per_week=3),
        )
    )
    query = "I want to lose weight. Male, 30 years old, 175 cm, 85 kg. Gym 3x/week. Goal: 75 kg"
    profile = extract_profile(
        query=query,
        profile={"days_per_week": 3},
    )
    assert profile["sex"] == "male"
    assert profile["age"] == 30
    assert profile["height_cm"] == 175
    assert profile["current_weight_kg"] == 85.0
    assert profile["target_weight_kg"] == 75.0
    assert "activity_level" not in profile
    assert profile["goal"] == "fat_loss"
    assert profile["days_per_week"] == 3
    assert "lose weight" in profile["query"]


def test_extract_profile_prefers_existing_user_profile(complete_profile: dict) -> None:
    configure_profile_extractor(
        lambda _query: (_ for _ in ()).throw(AssertionError("extractor should be skipped"))
    )
    profile = extract_profile(
        query="Male, 40 years old, 180 cm, 90 kg",
        profile=complete_profile,
    )
    assert profile["age"] == 30
    assert profile["height_cm"] == 175


def test_extract_profile_prefers_stored_profile_over_fresh_extraction() -> None:
    """Regression test for the flattened seed's merge-precedence invariant: unlike the
    skip-heuristic case above (`test_extract_profile_prefers_existing_user_profile`), this
    forces LLM extraction to actually run (the seed is incomplete) and proves the seed's
    already-known fields still beat what the extractor returns for those same fields, while
    extraction still fills in the fields the seed is missing.
    """
    configure_profile_extractor(
        lambda _query: ExtractedProfile(
            profile=Profile(age=99, height_cm=190, current_weight_kg=80),
            goal=Goal(goal="fat_loss", target_weight_kg=75),
        )
    )
    profile = extract_profile(
        query="I want to get fit.",
        profile={"age": 30, "height_cm": 175, "sex": "male"},
    )
    assert profile["age"] == 30, "stored age must beat the fresh extraction's age"
    assert profile["height_cm"] == 175, "stored height must beat the fresh extraction's height"
    assert profile["sex"] == "male"
    assert profile["current_weight_kg"] == 80.0, "extraction fills fields the seed is missing"
    assert profile["target_weight_kg"] == 75.0
    assert profile["goal"] == "fat_loss"


def test_extract_profile_parses_natural_language_query() -> None:
    configure_profile_extractor(
        lambda _query: ExtractedProfile(
            profile=Profile(age=27, height_cm=171, current_weight_kg=75),
            goal=Goal(goal="fat_loss", target_weight_kg=73),
        )
    )
    query = "im 27, 75kg, 171cm, i want to lose 2kg in 2 months"
    profile = extract_profile(query=query, profile={})
    assert profile["age"] == 27
    assert profile["height_cm"] == 171
    assert profile["current_weight_kg"] == 75.0
    assert profile["target_weight_kg"] == 73.0
    assert profile["goal"] == "fat_loss"


def test_extract_profile_parses_muscle_gain_query() -> None:
    configure_profile_extractor(
        lambda _query: ExtractedProfile(
            profile=Profile(age=27, height_cm=171, current_weight_kg=73),
            goal=Goal(goal="muscle_gain", target_weight_kg=75),
            constraints=Constraints(days_per_week=5),
        )
    )
    query = (
        "i want to gain 2 kg muscle, height 171cm, weight 73kg, age 27, training 5 days per week"
    )
    profile = extract_profile(
        query=query,
        profile={"days_per_week": 4, "equipment": "gym"},
    )
    assert profile["age"] == 27
    assert profile["height_cm"] == 171
    assert profile["current_weight_kg"] == 73.0
    assert profile["target_weight_kg"] == 75.0
    assert profile["goal"] == "muscle_gain"
    assert "activity_level" not in profile
    assert profile["days_per_week"] == 5


def test_extract_profile_uses_latest_hitl_segment_for_extraction() -> None:
    captured_queries: list[str] = []

    def _capture_extractor(query: str) -> ExtractedProfile:
        captured_queries.append(query)
        return ExtractedProfile(
            profile=Profile(sex="male"),
            goal=Goal(goal="fat_loss", target_weight_kg=75),
        )

    configure_profile_extractor(_capture_extractor)
    accumulated_query = (
        "I want to lose weight.\nMale, 30 years old, 175 cm, 85 kg. Gym 3x/week. Goal: 75 kg"
    )
    extract_profile(
        query=accumulated_query,
        profile={"age": 30},
    )
    assert captured_queries == ["Male, 30 years old, 175 cm, 85 kg. Gym 3x/week. Goal: 75 kg"]


def test_extract_profile_skips_extraction_when_profile_complete(complete_profile: dict) -> None:
    configure_profile_extractor(
        lambda _query: (_ for _ in ()).throw(AssertionError("extractor should be skipped"))
    )
    profile = extract_profile(
        query="I want to lose weight with a gym 3x/week plan.",
        profile=complete_profile,
    )
    assert (
        validate_profile_completeness(profile, derive_goal_spec(profile))[
            "feasibility_requires_review"
        ]
        is False
    )
    assert profile["age"] == 30
    assert profile["goal"] == "fat_loss"


def test_validate_profile_completeness_flags_missing_fields() -> None:
    profile = {"goal": "fat_loss"}
    result = validate_profile_completeness(profile, derive_goal_spec(profile))
    assert "age" in result["missing_fields"]
    assert "target_weight_kg" in result["missing_fields"]
    assert result["feasibility_requires_review"] is True


def test_validate_profile_completeness_passes_complete_profile(complete_profile: dict) -> None:
    result = validate_profile_completeness(complete_profile, derive_goal_spec(complete_profile))
    assert result["missing_fields"] == []
    assert result["feasibility_requires_review"] is False
