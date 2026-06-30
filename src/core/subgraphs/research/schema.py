"""Pydantic schemas for the Research Agent structured outputs."""

from typing import Any

from pydantic import BaseModel, ConfigDict, Field, field_validator


class TaskQueryPlan(BaseModel):
    """Optimized search queries for a single execution-plan task."""

    model_config = ConfigDict(extra="forbid")

    task_order: int = Field(ge=1)
    task: str = Field(min_length=5)
    queries: list[str] = Field(min_length=2, max_length=5)

    @field_validator("queries")
    @classmethod
    def validate_queries_non_empty(cls, queries: list[str]) -> list[str]:
        cleaned = [query.strip() for query in queries if query.strip()]
        if len(cleaned) < 2:
            raise ValueError("Each task must have at least 2 non-empty search queries")
        return cleaned


class SearchQueryBatch(BaseModel):
    """Batch of per-task search query plans."""

    model_config = ConfigDict(extra="forbid")

    task_plans: list[TaskQueryPlan] = Field(min_length=1)


class EvidenceEvaluation(BaseModel):
    """Assessment of whether gathered evidence is sufficient."""

    model_config = ConfigDict(extra="forbid")

    sufficient: bool
    gaps: list[str] = Field(default_factory=list)
    refined_queries: list[str] = Field(default_factory=list, max_length=3)

    @field_validator("refined_queries")
    @classmethod
    def validate_refined_queries(cls, queries: list[str]) -> list[str]:
        return [query.strip() for query in queries if query.strip()][:3]


class ResearchFindings(BaseModel):
    """Structured evidence synthesis for downstream agents."""

    model_config = ConfigDict(extra="forbid")

    consensus: str = Field(min_length=20)
    key_findings: list[str] = Field(min_length=1)
    conflicting_evidence: list[str] = Field(default_factory=list)
    limitations: list[str] = Field(default_factory=list)
    recommended_sources: list[str] = Field(default_factory=list)


class ResearchAgentResult(BaseModel):
    """Complete output from the Research Agent run."""

    model_config = ConfigDict(extra="forbid")

    sources: list[dict[str, Any]]
    evidence: list[dict[str, Any]]
    structured_findings: ResearchFindings
    evidence_summary: str
    agent_iterations: int = Field(ge=0)
