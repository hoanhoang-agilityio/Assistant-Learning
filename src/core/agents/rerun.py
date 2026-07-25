from typing import Any

from core.agents.state import RouteDecision

MAX_RETRY_COUNT = 2
MAX_REPLAN_COUNT = 1

STRUCTURAL_ISSUE_MARKERS = (
    "missing_macro_targets",
    "missing_training_plan",
    "draft_missing",
    "training_day_count_mismatch",
)


def replan_budget_remaining(replan_count: int) -> bool:
    """Whether a replan-triggering event may still increment replan_count
    without exceeding MAX_REPLAN_COUNT.

    The single source of truth both the AI-auto-replan path
    (partial_rerun_decision_data, below) and the user-initiated HITL revision
    path (core.hitl.resume.user_revision_to_replan_update) check before
    incrementing replan_count -- previously only the AI path did, letting a
    user request unlimited revisions with no bound.
    """
    return replan_count < MAX_REPLAN_COUNT


def partial_rerun_decision_data(
    verification_report: dict[str, Any],
    retry_count: int,
    replan_count: int,
    *,
    ordered_domains: list[str] | None = None,
) -> dict[str, Any]:
    if verification_report.get("passed"):
        return {"route_decision": "COMPLETE"}

    consistency_issues = verification_report.get("consistency", {}).get("issues", [])
    has_research = ordered_domains is None or "research" in ordered_domains

    if _has_structural_issues(consistency_issues):
        if replan_budget_remaining(replan_count):
            return {
                "route_decision": "REPLAN",
                "replan_count": replan_count + 1,
            }
        return _hitl_route()

    if has_research:
        citation_issues = verification_report.get("citation", {}).get("issues", [])
        ragas_pass = verification_report.get("ragas", {}).get("pass_fail", False)
        if not ragas_pass or _has_evidence_issues(citation_issues):
            if retry_count < MAX_RETRY_COUNT:
                return {
                    "route_decision": "RERESEARCH",
                    "retry_count": retry_count + 1,
                }
            return _hitl_route()

    if retry_count < MAX_RETRY_COUNT:
        return {
            "route_decision": "FIX_REASONING",
            "retry_count": retry_count + 1,
        }
    return _hitl_route()


def _has_structural_issues(consistency_issues: list[str]) -> bool:
    return any(
        any(marker in issue for marker in STRUCTURAL_ISSUE_MARKERS) for issue in consistency_issues
    )


def _has_evidence_issues(citation_issues: list[str]) -> bool:
    return any("source" in issue for issue in citation_issues)


def _hitl_route() -> dict[str, Any]:
    route_decision: RouteDecision = "HITL"
    return {
        "route_decision": route_decision,
        "waiting_for_user": True,
        "approval_status": "pending",
    }
