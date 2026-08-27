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


__all__ = [
    "FaithfulnessRoute",
    "GuardRoute",
    "HitlRoute",
    "Intent",
    "ProfileRoute",
    "VerificationRoute",
]
