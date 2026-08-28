"""Where each router's answer leads: one table per conditional edge in the graph."""

from langgraph.graph import END

from src.enums import (
    FaithfulnessRoute,
    GuardRoute,
    HitlAgentRoute,
    Node,
    SupervisorRoute,
    UserAgentRoute,
    VerificationRoute,
)

GUARD_ROUTES: dict[str, str] = {
    GuardRoute.BLOCKED: Node.BLOCKED,
    GuardRoute.PASS: Node.SUPERVISOR,
}

SUPERVISOR_ROUTES: dict[str, str] = {
    SupervisorRoute.USER_AGENT: Node.USER_AGENT,
    SupervisorRoute.COACH_AGENT: Node.COACH_AGENT,
    SupervisorRoute.QA_AGENT: Node.QA_AGENT,
    SupervisorRoute.FINISH: END,
}

USER_AGENT_ROUTES: dict[str, str] = {
    UserAgentRoute.PENDING_APPROVAL: Node.HITL_AGENT,
    UserAgentRoute.DONE: Node.SUMMARIZE,
}

VERIFICATION_ROUTES: dict[str, str] = {
    VerificationRoute.PASS: Node.PRESENT_PLAN,
    VerificationRoute.RETRY: Node.COACH_AGENT,
    VerificationRoute.EXHAUSTED: Node.NOTIFY_FAIL,
}

HITL_AGENT_ROUTES: dict[str, str] = {
    HitlAgentRoute.COACH_APPROVE: Node.COMMIT_PLAN,
    HitlAgentRoute.COACH_REVISE: Node.COACH_AGENT,
    HitlAgentRoute.COACH_NO_FEEDBACK: Node.HITL_REJECTED_NO_FEEDBACK,
    HitlAgentRoute.COACH_EXHAUSTED: Node.HITL_EXHAUSTED,
    HitlAgentRoute.USER_APPROVE: Node.COMMIT_PROFILE_UPDATE,
    HitlAgentRoute.USER_REJECT: Node.USER_AGENT,
}

FAITHFULNESS_ROUTES: dict[str, str] = {
    FaithfulnessRoute.PASS: Node.SUMMARIZE,
    FaithfulnessRoute.RETRY: Node.QA_AGENT,
    FaithfulnessRoute.FALLBACK: Node.QA_FALLBACK,
}

__all__ = [
    "FAITHFULNESS_ROUTES",
    "GUARD_ROUTES",
    "HITL_AGENT_ROUTES",
    "SUPERVISOR_ROUTES",
    "USER_AGENT_ROUTES",
    "VERIFICATION_ROUTES",
]
