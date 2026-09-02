"""Where each router's answer leads: one table per conditional edge in the graph."""

from langgraph.graph import END

from src.enums import (
    CoachRoute,
    FaithfulnessRoute,
    GuardRoute,
    Node,
    PlanApprovalRoute,
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
    UserAgentRoute.NEEDS_MORE_INFO: Node.DRAFT_PROFILE,
    UserAgentRoute.DONE: Node.SUMMARIZE,
}

VERIFICATION_ROUTES: dict[str, str] = {
    VerificationRoute.PASS: Node.PRESENT_PLAN,
    VerificationRoute.RETRY: Node.COACH_AGENT,
    VerificationRoute.EXHAUSTED: Node.NOTIFY_FAIL,
}

COACH_ROUTES: dict[str, str] = {
    CoachRoute.NEEDS_PROFILE: Node.SUMMARIZE,
    CoachRoute.ANSWERED: Node.SUMMARIZE,
    CoachRoute.READY: Node.DETERMINISTIC_VERIFICATION,
}

PLAN_APPROVAL_ROUTES: dict[str, str] = {
    PlanApprovalRoute.COACH_APPROVE: Node.COMMIT_PLAN,
    PlanApprovalRoute.COACH_REVISE: Node.COACH_AGENT,
    PlanApprovalRoute.COACH_NO_FEEDBACK: Node.HITL_REJECTED_NO_FEEDBACK,
    PlanApprovalRoute.COACH_EXHAUSTED: Node.HITL_EXHAUSTED,
}

FAITHFULNESS_ROUTES: dict[str, str] = {
    FaithfulnessRoute.PASS: Node.SUMMARIZE,
    FaithfulnessRoute.RETRY: Node.QA_AGENT,
    FaithfulnessRoute.FALLBACK: Node.QA_FALLBACK,
}

__all__ = [
    "COACH_ROUTES",
    "FAITHFULNESS_ROUTES",
    "GUARD_ROUTES",
    "PLAN_APPROVAL_ROUTES",
    "SUPERVISOR_ROUTES",
    "USER_AGENT_ROUTES",
    "VERIFICATION_ROUTES",
]
