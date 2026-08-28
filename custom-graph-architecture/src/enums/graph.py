"""Node names for the workflow graph, named once here rather than spelled out at each use."""

from enum import StrEnum


class Node(StrEnum):
    """Every node the workflow graph runs, in the order the graph reaches them."""

    GUARD_INPUT = "guard_input"
    BLOCKED = "blocked"
    SUPERVISOR = "supervisor"
    USER_AGENT = "user_agent"
    COACH_AGENT = "coach_agent"
    DETERMINISTIC_VERIFICATION = "deterministic_verification"
    PRESENT_PLAN = "present_plan"
    NOTIFY_FAIL = "notify_fail"
    HITL_AGENT = "hitl_agent"
    HITL_REJECTED_NO_FEEDBACK = "hitl_rejected_no_feedback"
    HITL_EXHAUSTED = "hitl_exhausted"
    COMMIT_PLAN = "commit_plan"
    COMMIT_PROFILE_UPDATE = "commit_profile_update"
    QA_AGENT = "qa_agent"
    VERIFY_FAITHFULNESS = "verify_faithfulness"
    QA_FALLBACK = "qa_fallback"
    SUMMARIZE = "summarize"


__all__ = ["Node"]
