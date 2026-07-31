from typing import Any, TypedDict


class UserState(TypedDict):
    """Scoped state for the User subgraph (profile intake/extraction/validation)."""

    query: str
    workspace_path: str
    revision_feedback: str | None

    profile: dict[str, Any]
    missing_fields: list[str]
    feasibility_issues: list[str]
    validation_errors: list[str]
    complete: bool
    valid: bool
    days_per_week_explicit: bool


class UserProfileResult(TypedDict):
    """Typed output contract the User subgraph exposes to the rest of the orchestration graph."""

    profile: dict[str, Any]
    complete: bool
    valid: bool
    missing_fields: list[str]
    feasibility_issues: list[str]
    validation_errors: list[str]
