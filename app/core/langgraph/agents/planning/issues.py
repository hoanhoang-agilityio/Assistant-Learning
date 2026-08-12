"""Issue construction shared by planning slot selection and plan patching."""

from app.schemas.graph import Issue


def make_planning_issue(
    severity: str,
    location: str,
    message: str,
    rubric_ref: str,
) -> Issue:
    """Build a planning issue with the shared source and empty suggestion."""
    return Issue(
        source="volume",
        severity=severity,
        location=location,
        message=message,
        suggestion=None,
        rubric_ref=rubric_ref,
    )


__all__ = ["make_planning_issue"]
