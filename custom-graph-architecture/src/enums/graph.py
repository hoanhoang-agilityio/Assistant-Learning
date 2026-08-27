"""Node names for the workflow graph, named once here rather than spelled out at each use."""

from enum import StrEnum


class Node(StrEnum):
    """Every node the workflow graph runs, in the order the graph reaches them."""

    GUARD_INPUT = "guard_input"
    BLOCKED = "blocked"
    PARSE_TURN = "parse_turn"
    OFF_TOPIC = "off_topic"
    LOAD_USER_CONTEXT = "load_user_context"
    MERGE_PROFILE = "merge_profile"
    PERSIST_PROFILE = "persist_profile"
    PERSIST_PREFERENCES = "persist_preferences"
    CHECK_PROFILE_COMPLETE = "check_profile_complete"
    REQUEST_MISSING_PROFILE_FIELDS = "request_missing_profile_fields"
    WAIT_FOR_USER = "wait_for_user"
    PROFILE_COLLECTION_EXHAUSTED = "profile_collection_exhausted"
    COACH_AGENT = "coach_agent"
    DETERMINISTIC_VERIFICATION = "deterministic_verification"
    PRESENT_PLAN = "present_plan"
    NOTIFY_FAIL = "notify_fail"
    HITL_REVIEW = "hitl_review"
    HITL_REJECTED_NO_FEEDBACK = "hitl_rejected_no_feedback"
    HITL_EXHAUSTED = "hitl_exhausted"
    QA_AGENT = "qa_agent"
    VERIFY_FAITHFULNESS = "verify_faithfulness"
    QA_FALLBACK = "qa_fallback"
    FINALIZE_TURN = "finalize_turn"


__all__ = ["Node"]
