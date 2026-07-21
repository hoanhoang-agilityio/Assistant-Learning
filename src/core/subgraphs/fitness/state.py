from typing import Literal, TypedDict


class FitnessState(TypedDict):
    """Scoped state for the Fitness subgraph."""

    workspace_path: str
    profile: dict
    constraints: dict
    days_per_week_explicit: bool
    execution_plan: dict
    structured_findings: dict | None
    evidence_summary: str | None
    verification_feedback: str | None
    plan_blueprint: dict
    macro_targets: dict
    training_constraints: dict
    structured_workout: dict | None
    safety_result: dict
    planner_feedback: list[str]
    planner_attempts: int
    max_planner_attempts: int
    is_verification_rerun: bool
    draft_plan: str | None
    template_fingerprint: str | None
    workout_source: (
        Literal["llm", "registry", "run_reuse", "llm_required", "deterministic_edit"] | None
    )
    reused_workout: bool
    edit_operation: dict | None
    previous_workout: dict | None
    edit_failed: bool
