"""Pydantic schemas for LLM-generated execution plans."""

from pydantic import BaseModel, ConfigDict, Field, field_validator


class PlanTask(BaseModel):
    """A single research-oriented task in the execution plan."""

    model_config = ConfigDict(extra="forbid")

    order: int = Field(ge=1)
    task: str = Field(min_length=10)
    rationale: str = Field(min_length=10)


class ExecutionPlan(BaseModel):
    """Structured execution plan returned by the Planning Agent."""

    model_config = ConfigDict(extra="forbid")

    plan_rationale: str = Field(min_length=20)
    tasks: list[PlanTask]
    plan_markdown: str = Field(min_length=50)
    template_id: str | None = None

    @field_validator("tasks")
    @classmethod
    def validate_tasks(cls, tasks: list[PlanTask]) -> list[PlanTask]:
        if len(tasks) < 3:
            raise ValueError("Execution plan must contain at least 3 tasks")
        if len(tasks) > 5:
            raise ValueError("Execution plan must contain at most 10 tasks")
        return tasks
