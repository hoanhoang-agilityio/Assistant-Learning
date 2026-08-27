"""Where each router's answer leads: one table per conditional edge in the graph."""

from src.enums import (
    FaithfulnessRoute,
    GuardRoute,
    HitlRoute,
    Intent,
    Node,
    ProfileRoute,
    VerificationRoute,
)

GUARD_ROUTES: dict[str, str] = {
    GuardRoute.BLOCKED: Node.BLOCKED,
    GuardRoute.PASS: Node.PARSE_TURN,
}

PARSE_ROUTES: dict[str, str] = {
    Intent.COACHING: Node.LOAD_USER_CONTEXT,
    Intent.QA: Node.LOAD_USER_CONTEXT,
    Intent.OFF_TOPIC: Node.OFF_TOPIC,
}

CONTEXT_ROUTES: dict[str, str] = {
    Intent.COACHING: Node.CHECK_PROFILE_COMPLETE,
    Intent.QA: Node.QA_AGENT,
}

PROFILE_ROUTES: dict[str, str] = {
    ProfileRoute.COMPLETE: Node.COACH_AGENT,
    ProfileRoute.ASK: Node.REQUEST_MISSING_PROFILE_FIELDS,
    ProfileRoute.EXHAUSTED: Node.PROFILE_COLLECTION_EXHAUSTED,
}

VERIFICATION_ROUTES: dict[str, str] = {
    VerificationRoute.PASS: Node.PRESENT_PLAN,
    VerificationRoute.RETRY: Node.COACH_AGENT,
    VerificationRoute.EXHAUSTED: Node.NOTIFY_FAIL,
}

FAITHFULNESS_ROUTES: dict[str, str] = {
    FaithfulnessRoute.PASS: Node.FINALIZE_TURN,
    FaithfulnessRoute.RETRY: Node.QA_AGENT,
    FaithfulnessRoute.FALLBACK: Node.QA_FALLBACK,
}

HITL_ROUTES: dict[str, str] = {
    HitlRoute.APPROVE: Node.FINALIZE_TURN,
    HitlRoute.REVISE: Node.COACH_AGENT,
    HitlRoute.NO_FEEDBACK: Node.HITL_REJECTED_NO_FEEDBACK,
    HitlRoute.EXHAUSTED: Node.HITL_EXHAUSTED,
}

__all__ = [
    "CONTEXT_ROUTES",
    "FAITHFULNESS_ROUTES",
    "GUARD_ROUTES",
    "HITL_ROUTES",
    "PARSE_ROUTES",
    "PROFILE_ROUTES",
    "VERIFICATION_ROUTES",
]
