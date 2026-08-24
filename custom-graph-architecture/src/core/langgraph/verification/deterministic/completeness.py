"""Schema completeness.

Pydantic already guarantees the plan's shape; this checks it is complete against its own
template. Every slot the template requires is filled exactly once, no prescription names a
slot the template does not have, the day count and numbering match, and every
``exercise_id`` resolves to a catalogue row — the check that stops an invented movement.
"""

from src.core.langgraph.verification.deterministic.context import PlanContext
from src.schemas import VerificationIssue


def check_completeness(context: PlanContext) -> list[VerificationIssue]:
    """Check the plan fills its template exactly, with real exercises."""

    raise NotImplementedError("task 5.1")
