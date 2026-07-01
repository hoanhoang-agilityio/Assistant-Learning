from typing import TypedDict


class FitnessState(TypedDict):
    """Scoped state for the Fitness subgraph."""

    workspace_path: str
    profile: dict
    constraints: dict
    execution_plan: dict
    structured_findings: dict | None
    evidence_summary: str | None
    verification_feedback: str | None
    macro_targets: dict
    training_constraints: dict
    structured_workout: dict | None
    safety_result: dict
    planner_feedback: list[str]
    planner_attempts: int
    max_planner_attempts: int
    is_verification_rerun: bool
    draft_plan: str | None
