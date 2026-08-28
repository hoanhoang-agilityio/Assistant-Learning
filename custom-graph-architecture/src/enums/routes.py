"""Branch labels: what each router in the graph may answer, and nothing else."""

from enum import StrEnum


class GuardRoute(StrEnum):
    """What ``route_after_guard`` may answer."""

    BLOCKED = "blocked"
    PASS = "pass"


class Intent(StrEnum):
    """The top-level intents, answered by ``route_after_parse`` and ``route_after_context``."""

    COACHING = "coaching"
    QA = "qa"
    OFF_TOPIC = "off_topic"


class ProfileRoute(StrEnum):
    """What ``route_after_profile_check`` may answer."""

    COMPLETE = "complete"
    ASK = "ask"
    EXHAUSTED = "exhausted"


class VerificationRoute(StrEnum):
    """What ``route_after_verification`` may answer."""

    PASS = "pass"
    RETRY = "retry"
    EXHAUSTED = "exhausted"


class FaithfulnessRoute(StrEnum):
    """What ``route_after_faithfulness`` may answer."""

    PASS = "pass"
    RETRY = "retry"
    FALLBACK = "fallback"


class HitlRoute(StrEnum):
    """What ``route_after_hitl_review`` may answer."""

    APPROVE = "approve"
    REVISE = "revise"
    NO_FEEDBACK = "no_feedback"
    EXHAUSTED = "exhausted"


class UserAgentRoute(StrEnum):
    """What ``route_after_user_agent`` may answer."""

    PENDING_APPROVAL = "pending_approval"
    DONE = "done"


class SupervisorRoute(StrEnum):
    """What ``route_after_supervisor`` may answer — the supervisor's own ``next`` decision."""

    USER_AGENT = "user_agent"
    COACH_AGENT = "coach_agent"
    QA_AGENT = "qa_agent"
    FINISH = "FINISH"


class HitlAgentRoute(StrEnum):
    """What ``route_after_hitl`` may answer, across both ``hitl_agent`` sources."""

    COACH_APPROVE = "coach_approve"
    COACH_REVISE = "coach_revise"
    COACH_NO_FEEDBACK = "coach_no_feedback"
    COACH_EXHAUSTED = "coach_exhausted"
    USER_APPROVE = "user_approve"
    USER_REJECT = "user_reject"


__all__ = [
    "FaithfulnessRoute",
    "GuardRoute",
    "HitlAgentRoute",
    "HitlRoute",
    "Intent",
    "ProfileRoute",
    "SupervisorRoute",
    "UserAgentRoute",
    "VerificationRoute",
]
