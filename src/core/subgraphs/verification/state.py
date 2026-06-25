from typing import TypedDict


class VerificationState(TypedDict):
    """Scoped state for the Verification subgraph."""

    verification_report: dict
    feedback: str | None
    faithfulness_score: float | None
    pass_fail: bool
