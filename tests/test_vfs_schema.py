import json

import pytest

from core.shared.planning.schema import ExecutionPlan
from core.vfs import (
    PLAN_EXECUTION_PLAN,
    PLAN_PROFILE,
    VFS_ARTIFACTS,
    VFS_SUBDIRS,
    parse_vfs_json_artifact,
    validate_vfs_json_artifact,
)
from core.vfs.bootstrap import RUN_SUBDIRS
from core.vfs.layout import (
    FITNESS_NORMALIZATION_FINDINGS,
    FITNESS_SAFETY_FLAGS,
    PLAN_REVISION_FEEDBACK,
    PLAN_SUBMITTED_TEXT,
    RESEARCH_SOURCES,
    get_artifact_spec,
    is_known_vfs_path,
)
from core.vfs.schema import ResearchSourcesArtifact, RevisionFeedback, SafetyFlagsArtifact


def test_vfs_subdirs_match_bootstrap_alias() -> None:
    assert VFS_SUBDIRS == RUN_SUBDIRS


def test_registry_contains_grounded_claims_artifacts() -> None:
    paths = {spec.path for spec in VFS_ARTIFACTS}
    assert "fitness/grounded_claims.json" in paths
    assert "fitness/grounded_claims.md" in paths


def test_get_artifact_spec_returns_metadata() -> None:
    spec = get_artifact_spec(PLAN_EXECUTION_PLAN)
    assert spec is not None
    assert spec.producer == "planning"
    assert spec.content_kind.value == "json"


def test_registry_contains_phase_4_artifacts() -> None:
    paths = {spec.path for spec in VFS_ARTIFACTS}
    assert PLAN_SUBMITTED_TEXT in paths
    assert FITNESS_NORMALIZATION_FINDINGS in paths
    assert get_artifact_spec(PLAN_SUBMITTED_TEXT).producer == "orchestration"
    assert get_artifact_spec(FITNESS_NORMALIZATION_FINDINGS).producer == "fitness"


def test_is_known_vfs_path() -> None:
    assert is_known_vfs_path(PLAN_EXECUTION_PLAN) is True
    assert is_known_vfs_path("plan/todos.json") is False


def test_validate_execution_plan_artifact() -> None:
    payload = {
        "plan_rationale": "Research plan tailored for fat_loss with evidence gathering.",
        "tasks": [
            {
                "order": 1,
                "task": "Research evidence-based training principles for fat_loss",
                "rationale": "Establish foundational evidence for the user's fat_loss goal.",
            },
            {
                "order": 2,
                "task": "Gather activity-level training volume recommendations",
                "rationale": "Match training frequency to the user's current activity level.",
            },
            {
                "order": 3,
                "task": "Collect macro and recovery guidance aligned with user constraints",
                "rationale": "Support nutrition and recovery decisions with credible sources.",
            },
        ],
        "plan_markdown": "# Planning Summary\n\n- Goal: fat_loss\n- Tasks: 3 research-oriented steps\n",
    }
    artifact = validate_vfs_json_artifact(PLAN_EXECUTION_PLAN, payload)
    assert isinstance(artifact, ExecutionPlan)
    assert len(artifact.tasks) == 3


def test_parse_revision_feedback_artifact() -> None:
    raw = json.dumps({"feedback": "Reduce training volume to 3 days"})
    artifact = parse_vfs_json_artifact(PLAN_REVISION_FEEDBACK, raw)
    assert isinstance(artifact, RevisionFeedback)
    assert artifact.feedback == "Reduce training volume to 3 days"


def test_validate_profile_snapshot_allows_compact_fields() -> None:
    artifact = validate_vfs_json_artifact(
        PLAN_PROFILE,
        {"goal": "fat_loss", "age": 30, "days_per_week": 3},
    )
    assert artifact.model_dump()["goal"] == "fat_loss"


def test_validate_research_sources_list() -> None:
    artifact = validate_vfs_json_artifact(
        RESEARCH_SOURCES,
        [
            {
                "title": "Hypertrophy training evidence",
                "url": "https://example.edu/fitness-training",
                "provider": "tavily",
            }
        ],
    )
    assert isinstance(artifact, ResearchSourcesArtifact)
    assert len(artifact.root) == 1


def test_validate_safety_flags_list() -> None:
    artifact = validate_vfs_json_artifact(FITNESS_SAFETY_FLAGS, ["training_day_count_mismatch"])
    assert isinstance(artifact, SafetyFlagsArtifact)
    assert artifact.root == ["training_day_count_mismatch"]


def test_validate_execution_plan_rejects_short_plan() -> None:
    payload = {
        "plan_rationale": "Too short",
        "tasks": [
            {
                "order": 1,
                "task": "Only one task here",
                "rationale": "Not enough tasks for a valid plan.",
            }
        ],
        "plan_markdown": "short",
    }
    with pytest.raises(Exception):
        validate_vfs_json_artifact(PLAN_EXECUTION_PLAN, payload)


def test_validate_unknown_path_raises() -> None:
    with pytest.raises(KeyError, match="No JSON schema registered"):
        validate_vfs_json_artifact("plan/todos.json", [])
