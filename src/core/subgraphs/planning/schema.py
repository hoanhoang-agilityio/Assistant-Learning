"""Pydantic schemas for LLM-generated execution plans."""

from pydantic import BaseModel, ConfigDict, Field


class PlanTask(BaseModel):
    """A single research-oriented task in the execution plan."""

    model_config = ConfigDict(extra="forbid")

    order: int = Field(ge=1, description="Execution order (1-based)")
    task: str = Field(min_length=10, description="Actionable research task")
    rationale: str = Field(min_length=10, description="Why this task matters for this user")


class ExecutionPlan(BaseModel):
    """Structured execution plan returned by the Planning Agent."""

    model_config = ConfigDict(extra="forbid")

    plan_rationale: str = Field(min_length=20, description="Overall plan rationale")
    tasks: list[PlanTask] = Field(min_length=3, max_length=10)
    plan_markdown: str = Field(min_length=50, description="Human-readable planning summary")
