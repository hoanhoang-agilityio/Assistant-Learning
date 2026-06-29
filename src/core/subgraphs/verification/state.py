from typing import TypedDict


class VerificationState(TypedDict):
    """Scoped state for the Verification subgraph."""

    workspace_path: str
    draft_plan: str
    sources: list[dict]
    evidence: list[dict]
    macro_targets: dict
    training_plan: dict
    profile: dict
    constraints: dict
    safety_flags: list[str]
    verification_report: dict
    feedback: str | None
    faithfulness_score: float | None
    pass_fail: bool
