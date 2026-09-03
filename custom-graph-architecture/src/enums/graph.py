"""Node names for the workflow graph, named once here rather than spelled out at each use."""

from enum import StrEnum


class Node(StrEnum):
    """Every node the workflow graph runs, in the order the graph reaches them."""

    GUARD_INPUT = "guard_input"
    BLOCKED = "blocked"
    SUPERVISOR = "supervisor"
    USER_AGENT = "user_agent"
    COACH_AGENT = "coach_agent"
    DRAFT_PROFILE = "draft_profile"
    COLLECT_PROFILE = "collect_profile"
    DETERMINISTIC_VERIFICATION = "deterministic_verification"
    PRESENT_PLAN = "present_plan"
    NOTIFY_FAIL = "notify_fail"
    PLAN_APPROVAL = "plan_approval"
    HITL_REJECTED_NO_FEEDBACK = "hitl_rejected_no_feedback"
    HITL_EXHAUSTED = "hitl_exhausted"
    COMMIT_PLAN = "commit_plan"
    QA_AGENT = "qa_agent"
    VERIFY_FAITHFULNESS = "verify_faithfulness"
    QA_FALLBACK = "qa_fallback"


__all__ = ["Node"]
