"""Pydantic schemas for the Research Agent structured outputs."""

import re
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, field_validator


def _coerce_string_list(value: Any) -> list[str]:
    """Normalize LLM outputs that return a prose/numbered string instead of a JSON array."""
    if value is None:
        return []
    if isinstance(value, list):
        return [str(item).strip() for item in value if str(item).strip()]
    if not isinstance(value, str):
        return value
    text = value.strip()
    if not text:
        return []
    lines = re.split(r"\n+", text)
    items: list[str] = []
    for line in lines:
        cleaned = line.strip()
        if not cleaned:
            continue
        cleaned = re.sub(r"^\d+[\.\)]\s*", "", cleaned)
        cleaned = re.sub(r"^[-*•]\s*", "", cleaned).strip()
        if cleaned:
            items.append(cleaned)
    if items:
        return items
    cleaned = re.sub(r"^\d+[\.\)]\s*", "", text).strip()
    return [cleaned] if cleaned else []


class TaskQueryPlan(BaseModel):
    """Optimized search queries for a single execution-plan task."""

    model_config = ConfigDict(extra="forbid")

    task_order: int = Field(ge=1)
    task: str = Field(min_length=5)
    queries: list[str]

    @field_validator("queries")
    @classmethod
    def validate_queries_non_empty(cls, queries: list[str]) -> list[str]:
        cleaned = [query.strip() for query in queries if query.strip()]
        if len(cleaned) < 1:
            raise ValueError("Each task must have at least 1 non-empty search queries")
        if len(cleaned) > 3:
            raise ValueError("Each task must have at most 3 non-empty search queries")
        return cleaned


class SearchQueryBatch(BaseModel):
    """Batch of per-task search query plans."""

    model_config = ConfigDict(extra="forbid")

    task_plans: list[TaskQueryPlan]

    @field_validator("task_plans")
    @classmethod
    def validate_task_plans(cls, task_plans: list[TaskQueryPlan]) -> list[TaskQueryPlan]:
        if not task_plans:
            raise ValueError("Search query batch must contain at least one task plan")
        return task_plans


class EvidenceEvaluation(BaseModel):
    """Assessment of whether gathered evidence is sufficient."""

    model_config = ConfigDict(extra="forbid")

    sufficient: bool
    gaps: list[str] = Field(default_factory=list)
    refined_queries: list[str] = Field(default_factory=list)

    @field_validator("gaps", mode="before")
    @classmethod
    def coerce_gaps(cls, gaps: Any) -> Any:
        if isinstance(gaps, str):
            return _coerce_string_list(gaps)
        return gaps

    @field_validator("refined_queries", mode="before")
    @classmethod
    def coerce_refined_queries(cls, queries: Any) -> Any:
        if isinstance(queries, str):
            return _coerce_string_list(queries)
        return queries

    @field_validator("refined_queries")
    @classmethod
    def validate_refined_queries(cls, queries: list[str]) -> list[str]:
        return [query.strip() for query in queries if query.strip()][:3]


class ResearchFindings(BaseModel):
    """Structured evidence synthesis for downstream agents."""

    model_config = ConfigDict(extra="forbid")

    consensus: str = Field(min_length=20)
    key_findings: list[str]
    conflicting_evidence: list[str] = Field(default_factory=list)
    limitations: list[str] = Field(default_factory=list)
    recommended_sources: list[str] = Field(default_factory=list)

    @field_validator(
        "key_findings",
        "conflicting_evidence",
        "limitations",
        "recommended_sources",
        mode="before",
    )
    @classmethod
    def coerce_list_fields(cls, value: Any) -> Any:
        if isinstance(value, str):
            return _coerce_string_list(value)
        return value

    @field_validator("key_findings")
    @classmethod
    def validate_key_findings(cls, findings: list[str]) -> list[str]:
        if not findings:
            raise ValueError("key_findings must contain at least one item")
        return findings


class ResearchAgentResult(BaseModel):
    """Complete output from the Research Agent run."""

    model_config = ConfigDict(extra="forbid")

    sources: list[dict[str, Any]]
    evidence: list[dict[str, Any]]
    structured_findings: ResearchFindings
    evidence_summary: str
    agent_iterations: int = Field(ge=0)
