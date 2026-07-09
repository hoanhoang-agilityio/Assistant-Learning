"""Pydantic schemas and validation helpers for canonical VFS artifacts."""

from __future__ import annotations

import json
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, RootModel, model_validator

from core.vfs.layout import (
    FITNESS_CALCULATIONS,
    FITNESS_SAFETY_FLAGS,
    FITNESS_TEMPLATE_FINGERPRINT,
    FITNESS_WORKOUT,
    LOGS_METRICS,
    LOGS_PERSIST_RESULT,
    LOGS_RUN_SNAPSHOT,
    PLAN_EXECUTION_PLAN,
    PLAN_PROFILE,
    PLAN_REVISION_FEEDBACK,
    RESEARCH_FINDINGS,
    RESEARCH_SOURCES,
    VERIFY_RAGAS,
    VERIFY_REPORT,
)


class RevisionFeedback(BaseModel):
    """User revision text persisted between REPLAN runs."""

    model_config = ConfigDict(extra="forbid")

    feedback: str = Field(min_length=1)


class ProfileSnapshot(BaseModel):
    """Compact profile snapshot written to plan/profile.json."""

    model_config = ConfigDict(extra="allow")

    age: int | None = None
    sex: str | None = None
    height_cm: float | None = None
    current_weight_kg: float | None = None
    target_weight_kg: float | None = None
    weight_delta_kg: float | None = None
    horizon_weeks: int | None = None
    weekly_rate_kg: float | None = None
    goal_archetype: str | None = None
    feasibility_level: str | None = None
    activity_level: str | None = None
    goal: str | None = None
    days_per_week: int | None = None
    equipment: str | None = None
    session_duration_minutes: int | None = None
    high_protein: bool | None = None


class ResearchSource(BaseModel):
    """A single research source persisted to research/sources.json."""

    model_config = ConfigDict(extra="allow")

    source_id: str | None = None
    title: str
    url: str
    snippet: str | None = None
    score: float | None = None
    provider: str


class ResearchSourcesArtifact(RootModel[list[ResearchSource]]):
    """List wrapper for research/sources.json."""


class ResearchEvidenceItem(BaseModel):
    """Evidence chunk referenced by downstream verification."""

    model_config = ConfigDict(extra="allow")

    document_id: str | None = None
    url: str | None = None
    content: str | None = None
    provider: str | None = None


class ResearchFindingsArtifact(BaseModel):
    """Wrapper persisted to research/findings.json."""

    model_config = ConfigDict(extra="forbid")

    structured_findings: dict[str, Any]
    evidence: list[ResearchEvidenceItem]
    evidence_summary: str
    source_count: int = Field(ge=0)
    local_source_count: int = Field(default=0, ge=0)

    @model_validator(mode="after")
    def validate_structured_findings(self) -> ResearchFindingsArtifact:
        from core.subgraphs.research.schema import ResearchFindings

        ResearchFindings.model_validate(self.structured_findings)
        return self


class WorkoutSummary(BaseModel):
    """Compact workout summary embedded in fitness/calculations.json."""

    model_config = ConfigDict(extra="forbid")

    split: str
    goal: str
    weekly_sets: int = Field(ge=1)
    sessions: int = Field(ge=0)


class FitnessCalculations(BaseModel):
    """Macro targets and workout summary persisted to fitness/calculations.json."""

    model_config = ConfigDict(extra="allow")

    macro_targets: dict[str, Any]
    workout_summary: WorkoutSummary
    training_plan_summary: WorkoutSummary | None = None
    plan_blueprint: dict[str, Any] | None = None


class TemplateFingerprint(BaseModel):
    """Template registry metadata for deterministic workout reuse."""

    model_config = ConfigDict(extra="forbid")

    fingerprint: str = Field(min_length=1)
    workout_source: str | None = None


class SafetyFlagsArtifact(RootModel[list[str]]):
    """List wrapper for fitness/safety_flags.json."""


class VerificationCheckResult(BaseModel):
    """Shared shape for citation, consistency, and safety checks."""

    model_config = ConfigDict(extra="allow")

    passed: bool
    issues: list[str] = Field(default_factory=list)


class CitationCheckResult(VerificationCheckResult):
    """Citation check result embedded in verify/verification_v1.json."""

    cited_source_count: int = Field(default=0, ge=0)


class RagasFaithfulness(BaseModel):
    """Faithfulness scoring payload persisted to verify/ragas.json."""

    model_config = ConfigDict(extra="forbid")

    faithfulness_score: float = Field(ge=0.0, le=1.0)
    pass_fail: bool
    method: str
    threshold: float = Field(ge=0.0, le=1.0)


class VerificationReport(BaseModel):
    """Full verification report persisted to verify/verification_v1.json."""

    model_config = ConfigDict(extra="forbid")

    citation: CitationCheckResult
    consistency: VerificationCheckResult
    safety: VerificationCheckResult
    ragas: RagasFaithfulness
    passed: bool
    feedback: str | None = None


class RunSnapshot(BaseModel):
    """Orchestration snapshot persisted to logs/run_snapshot.json."""

    model_config = ConfigDict(extra="allow")

    run_id: str
    thread_id: str
    query: str | None = None
    request_type: str | None = None
    route_decision: str | None = None
    verification_passed: bool | None = None
    faithfulness_score: float | None = None
    approval_status: str | None = None
    persisted_at: str


class RunMetrics(BaseModel):
    """Run metrics persisted to logs/metrics.json."""

    model_config = ConfigDict(extra="forbid")

    run_id: str
    faithfulness_score: float | None = None
    verification_passed: bool
    ragas: dict[str, Any] = Field(default_factory=dict)
    persisted_at: str


class PersistResult(BaseModel):
    """Persist stage output persisted to logs/persist_result.json."""

    model_config = ConfigDict(extra="forbid")

    persisted_at: str
    artifacts: list[str]
    final_artifact_path: str


class SupervisorDecisionEntry(BaseModel):
    """Single JSONL line in logs/supervisor_decisions.jsonl."""

    model_config = ConfigDict(extra="allow")

    route_decision: str
    verification_passed: bool | None = None
    retry_count: int | None = None
    replan_count: int | None = None


def _vfs_json_schemas() -> dict[str, type[BaseModel]]:
    from core.subgraphs.fitness.schema import StructuredWorkout
    from core.subgraphs.planning.schema import ExecutionPlan

    return {
        PLAN_EXECUTION_PLAN: ExecutionPlan,
        PLAN_PROFILE: ProfileSnapshot,
        PLAN_REVISION_FEEDBACK: RevisionFeedback,
        RESEARCH_SOURCES: ResearchSourcesArtifact,
        RESEARCH_FINDINGS: ResearchFindingsArtifact,
        FITNESS_WORKOUT: StructuredWorkout,
        FITNESS_CALCULATIONS: FitnessCalculations,
        FITNESS_TEMPLATE_FINGERPRINT: TemplateFingerprint,
        FITNESS_SAFETY_FLAGS: SafetyFlagsArtifact,
        VERIFY_REPORT: VerificationReport,
        VERIFY_RAGAS: RagasFaithfulness,
        LOGS_RUN_SNAPSHOT: RunSnapshot,
        LOGS_METRICS: RunMetrics,
        LOGS_PERSIST_RESULT: PersistResult,
    }


def validate_vfs_json_artifact(path: str, payload: Any) -> BaseModel:
    """Validate a parsed JSON payload against the schema for a canonical VFS path."""
    schema = _vfs_json_schemas().get(path)
    if schema is None:
        raise KeyError(f"No JSON schema registered for VFS path: {path}")
    return schema.model_validate(payload)


def parse_vfs_json_artifact(path: str, raw: str) -> BaseModel:
    """Parse and validate a JSON VFS artifact from its raw file contents."""
    return validate_vfs_json_artifact(path, json.loads(raw))
