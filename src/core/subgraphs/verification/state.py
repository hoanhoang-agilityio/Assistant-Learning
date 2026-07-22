from typing import TypedDict


class VerificationState(TypedDict):
    """Scoped state for the Verification subgraph."""

    workspace_path: str
    draft_plan: str
    sources: list[dict]
    evidence: list[dict]
    macro_targets: dict
    training_plan: dict
    safety_flags: list[str]
    plan_blueprint: dict
    verification_report: dict
    faithfulness_score: float | None
