"""Canonical VFS workspace layout and artifact registry."""

from __future__ import annotations

from enum import StrEnum
from typing import Literal

from pydantic import BaseModel, ConfigDict

VFS_SUBDIRS: tuple[str, ...] = ("plan", "research", "fitness", "verify", "final", "logs")

PLAN_EXECUTION_PLAN = "plan/execution_plan.json"
PLAN_MARKDOWN = "plan/plan.md"
PLAN_PROFILE = "plan/profile.json"
PLAN_REVISION_FEEDBACK = "plan/revision_feedback.json"
PLAN_SUBMITTED_TEXT = "plan/submitted_plan.md"

RESEARCH_SOURCES = "research/sources.json"
RESEARCH_FINDINGS = "research/findings.json"

FITNESS_WORKOUT = "fitness/workout.json"
FITNESS_CALCULATIONS = "fitness/calculations.json"
FITNESS_BLUEPRINT = "fitness/blueprint.json"
FITNESS_TEMPLATE_FINGERPRINT = "fitness/template_fingerprint.json"
FITNESS_SAFETY_FLAGS = "fitness/safety_flags.json"
FITNESS_NORMALIZATION_FINDINGS = "fitness/normalization_findings.json"
FITNESS_FINAL_PLAN = "fitness/final_plan.md"

VERIFY_REPORT = "verify/verification_v1.json"
VERIFY_RAGAS = "verify/ragas.json"

FINAL_PLAN = "final/final_plan.md"
FINAL_WORKOUT = "final/workout.json"
FINAL_CALCULATIONS = "final/calculations.json"
FINAL_BLUEPRINT = "final/blueprint.json"
FINAL_RESEARCH_SOURCES = "final/research_sources.json"
FINAL_VERIFICATION_REPORT = "final/verification_report.json"

LOGS_RUN_SNAPSHOT = "logs/run_snapshot.json"
LOGS_METRICS = "logs/metrics.json"
LOGS_PERSIST_RESULT = "logs/persist_result.json"
LOGS_SUPERVISOR_DECISIONS = "logs/supervisor_decisions.jsonl"
LOGS_TOKEN_COST_LOG = "logs/token_cost.log"
LOGS_TOKEN_COST_MARKDOWN = "logs/token_cost.md"

type VfsArtifactPath = Literal[
    "plan/execution_plan.json",
    "plan/plan.md",
    "plan/profile.json",
    "plan/revision_feedback.json",
    "plan/submitted_plan.md",
    "research/sources.json",
    "research/findings.json",
    "fitness/workout.json",
    "fitness/calculations.json",
    "fitness/blueprint.json",
    "fitness/template_fingerprint.json",
    "fitness/safety_flags.json",
    "fitness/normalization_findings.json",
    "fitness/final_plan.md",
    "verify/verification_v1.json",
    "verify/ragas.json",
    "final/final_plan.md",
    "final/workout.json",
    "final/calculations.json",
    "final/blueprint.json",
    "final/research_sources.json",
    "final/verification_report.json",
    "logs/run_snapshot.json",
    "logs/metrics.json",
    "logs/persist_result.json",
    "logs/supervisor_decisions.jsonl",
    "logs/token_cost.log",
    "logs/token_cost.md",
]


class VfsContentKind(StrEnum):
    JSON = "json"
    MARKDOWN = "markdown"
    JSONL = "jsonl"
    TEXT = "text"


class VfsArtifactSpec(BaseModel):
    """Registry entry describing one canonical VFS artifact."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    path: VfsArtifactPath
    content_kind: VfsContentKind
    producer: str
    description: str


VFS_ARTIFACTS: tuple[VfsArtifactSpec, ...] = (
    VfsArtifactSpec(
        path=PLAN_EXECUTION_PLAN,
        content_kind=VfsContentKind.JSON,
        producer="planning",
        description="Canonical execution plan gate for research and fitness",
    ),
    VfsArtifactSpec(
        path=PLAN_MARKDOWN,
        content_kind=VfsContentKind.MARKDOWN,
        producer="planning",
        description="Human-readable planning summary",
    ),
    VfsArtifactSpec(
        path=PLAN_PROFILE,
        content_kind=VfsContentKind.JSON,
        producer="planning",
        description="Compact validated profile snapshot",
    ),
    VfsArtifactSpec(
        path=PLAN_REVISION_FEEDBACK,
        content_kind=VfsContentKind.JSON,
        producer="orchestration",
        description="User revision feedback for a Fitness revision resume",
    ),
    VfsArtifactSpec(
        path=PLAN_SUBMITTED_TEXT,
        content_kind=VfsContentKind.MARKDOWN,
        producer="orchestration",
        description="User-submitted existing plan text for verify_plan runs",
    ),
    VfsArtifactSpec(
        path=RESEARCH_SOURCES,
        content_kind=VfsContentKind.JSON,
        producer="research",
        description="Collected research sources",
    ),
    VfsArtifactSpec(
        path=RESEARCH_FINDINGS,
        content_kind=VfsContentKind.JSON,
        producer="research",
        description="Structured evidence synthesis and raw evidence",
    ),
    VfsArtifactSpec(
        path=FITNESS_WORKOUT,
        content_kind=VfsContentKind.JSON,
        producer="fitness",
        description="Structured workout prescription",
    ),
    VfsArtifactSpec(
        path=FITNESS_CALCULATIONS,
        content_kind=VfsContentKind.JSON,
        producer="fitness",
        description="Macro targets and workout summary",
    ),
    VfsArtifactSpec(
        path=FITNESS_BLUEPRINT,
        content_kind=VfsContentKind.JSON,
        producer="fitness",
        description="Program blueprint metadata",
    ),
    VfsArtifactSpec(
        path=FITNESS_TEMPLATE_FINGERPRINT,
        content_kind=VfsContentKind.JSON,
        producer="fitness",
        description="Template registry fingerprint for workout reuse",
    ),
    VfsArtifactSpec(
        path=FITNESS_SAFETY_FLAGS,
        content_kind=VfsContentKind.JSON,
        producer="fitness",
        description="Deterministic safety feedback flags",
    ),
    VfsArtifactSpec(
        path=FITNESS_NORMALIZATION_FINDINGS,
        content_kind=VfsContentKind.JSON,
        producer="fitness",
        description=(
            "Findings recorded when a submitted external plan's structure conflicts with "
            "the profile-derived blueprint (design review F7); always written by evaluate "
            "mode, possibly empty"
        ),
    ),
    VfsArtifactSpec(
        path=FITNESS_FINAL_PLAN,
        content_kind=VfsContentKind.MARKDOWN,
        producer="fitness",
        description="Draft fitness plan consumed by verification",
    ),
    VfsArtifactSpec(
        path=VERIFY_REPORT,
        content_kind=VfsContentKind.JSON,
        producer="verification",
        description="Citation, consistency, safety, and faithfulness report",
    ),
    VfsArtifactSpec(
        path=VERIFY_RAGAS,
        content_kind=VfsContentKind.JSON,
        producer="verification",
        description="Faithfulness scoring payload",
    ),
    VfsArtifactSpec(
        path=FINAL_PLAN,
        content_kind=VfsContentKind.MARKDOWN,
        producer="persist",
        description="Approved final plan delivered to the user",
    ),
    VfsArtifactSpec(
        path=FINAL_WORKOUT,
        content_kind=VfsContentKind.JSON,
        producer="persist",
        description="Copy of fitness/workout.json archived at persist time",
    ),
    VfsArtifactSpec(
        path=FINAL_CALCULATIONS,
        content_kind=VfsContentKind.JSON,
        producer="persist",
        description="Copy of fitness/calculations.json archived at persist time",
    ),
    VfsArtifactSpec(
        path=FINAL_BLUEPRINT,
        content_kind=VfsContentKind.JSON,
        producer="persist",
        description="Copy of fitness/blueprint.json archived at persist time",
    ),
    VfsArtifactSpec(
        path=FINAL_RESEARCH_SOURCES,
        content_kind=VfsContentKind.JSON,
        producer="persist",
        description="Copy of research/sources.json archived at persist time",
    ),
    VfsArtifactSpec(
        path=FINAL_VERIFICATION_REPORT,
        content_kind=VfsContentKind.JSON,
        producer="persist",
        description="Copy of verify/verification_v1.json archived at persist time",
    ),
    VfsArtifactSpec(
        path=LOGS_RUN_SNAPSHOT,
        content_kind=VfsContentKind.JSON,
        producer="persist",
        description="Orchestration snapshot at persist time",
    ),
    VfsArtifactSpec(
        path=LOGS_METRICS,
        content_kind=VfsContentKind.JSON,
        producer="persist",
        description="Run-level verification and faithfulness metrics",
    ),
    VfsArtifactSpec(
        path=LOGS_PERSIST_RESULT,
        content_kind=VfsContentKind.JSON,
        producer="persist",
        description="Persist stage artifact manifest",
    ),
    VfsArtifactSpec(
        path=LOGS_SUPERVISOR_DECISIONS,
        content_kind=VfsContentKind.JSONL,
        producer="supervisor",
        description="Append-only supervisor routing decisions",
    ),
    VfsArtifactSpec(
        path=LOGS_TOKEN_COST_LOG,
        content_kind=VfsContentKind.TEXT,
        producer="graph",
        description="Plain-text token usage and cost summary for the run",
    ),
    VfsArtifactSpec(
        path=LOGS_TOKEN_COST_MARKDOWN,
        content_kind=VfsContentKind.MARKDOWN,
        producer="graph",
        description="Markdown token usage and cost summary for the run",
    ),
)

VFS_ARTIFACT_PATHS: frozenset[str] = frozenset(spec.path for spec in VFS_ARTIFACTS)


def get_artifact_spec(path: str) -> VfsArtifactSpec | None:
    """Return registry metadata for a canonical VFS path."""
    for spec in VFS_ARTIFACTS:
        if spec.path == path:
            return spec
    return None


def is_known_vfs_path(path: str) -> bool:
    """Return whether the path is part of the canonical VFS registry."""
    return path in VFS_ARTIFACT_PATHS
