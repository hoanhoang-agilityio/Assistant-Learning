"""What the deterministic gate reports back about a plan.

An issue is written for the coach agent to act on, not for a log line: it names the rule
that fired, the part of the plan that broke it and what to do instead. ``build_coach_input``
serialises the whole result into the revision prompt, so every field here is something the
agent is expected to read.
"""

from enum import StrEnum

from pydantic import BaseModel, Field


class CheckName(StrEnum):
    """The deterministic rules."""

    COMPLETENESS = "completeness"
    AVAILABILITY = "availability"


class Severity(StrEnum):
    """Whether an issue fails the gate. Every deterministic issue fails it."""

    ERROR = "error"
    WARNING = "warning"


class VerificationIssue(BaseModel):
    """One broken rule, located in the plan."""

    check: CheckName = Field(description="The rule that fired.")
    message: str = Field(
        description="What is wrong and what to change, addressed to the coach agent."
    )
    severity: Severity = Field(
        default=Severity.ERROR, description="Whether this fails the gate."
    )
    day_number: int | None = Field(
        default=None,
        ge=1,
        description="Training day the issue is in, when it is in one.",
    )
    slot_id: str | None = Field(default=None, description="Slot the issue is about.")
    exercise_id: str | None = Field(
        default=None, description="Prescribed exercise the issue is about."
    )
    field: str | None = Field(
        default=None,
        description="Plan field the issue is about, for issues tied to no slot.",
    )


class VerificationResult(BaseModel):
    """The gate's verdict on one plan.

    ``passed`` is derived rather than set: a result cannot claim to pass while holding an
    error, which is the one invariant the routing in ``verify_plan`` depends on.
    """

    issues: list[VerificationIssue] = Field(
        default_factory=list, description="Every issue found, errors and warnings."
    )

    @property
    def errors(self) -> list[VerificationIssue]:
        """The issues that fail the gate."""
        return [issue for issue in self.issues if issue.severity is Severity.ERROR]

    @property
    def warnings(self) -> list[VerificationIssue]:
        """The issues reported without failing the gate."""
        return [issue for issue in self.issues if issue.severity is Severity.WARNING]

    @property
    def passed(self) -> bool:
        """Whether the plan may go on to human review."""
        return not self.errors
