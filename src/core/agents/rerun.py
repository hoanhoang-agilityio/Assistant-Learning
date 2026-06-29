from typing import Any

from core.agents.state import RouteDecision

MAX_RETRY_COUNT = 3
MAX_REPLAN_COUNT = 2

STRUCTURAL_ISSUE_MARKERS = (
    "missing_macro_targets",
    "missing_training_plan",
    "draft_missing",
    "training_day_count_mismatch",
)


def partial_rerun_decision_data(
    verification_report: dict[str, Any],
    retry_count: int,
    replan_count: int,
) -> dict[str, Any]:
    """Select partial rerun route after a failed verification report."""
    if verification_report.get("passed"):
        return {"route_decision": "COMPLETE"}

    consistency_issues = verification_report.get("consistency", {}).get("issues", [])
    citation_issues = verification_report.get("citation", {}).get("issues", [])
    ragas_pass = verification_report.get("ragas", {}).get("pass_fail", False)

    if _has_structural_issues(consistency_issues):
        if replan_count < MAX_REPLAN_COUNT:
            return {
                "route_decision": "REPLAN",
                "replan_count": replan_count + 1,
            }
        return _hitl_route()

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
