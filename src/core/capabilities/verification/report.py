"""Turning the individual check results into one verification report, and
deciding which capability owns fixing a failure."""

from typing import Any

from core.capabilities.verification.checks.faithfulness import FAITHFULNESS_PASS_THRESHOLD

_REPORT_LABELS: tuple[tuple[str, str], ...] = (
    ("citation", "Citation"),
    ("consistency", "Consistency"),
    ("safety", "Safety"),
)

# Which capability owns fixing a failing check -- research owns evidence/
# citations, fitness owns the macro/workout numbers it computed itself.
# "ragas" (faithfulness) is a research-owned failure: a low score means the
# draft's claims aren't actually supported by the evidence research gathered,
# which fitness has no way to fix by regenerating a workout.
_CHECK_OWNERS: dict[str, str] = {
    "citation": "research",
    "ragas": "research",
    "consistency": "fitness",
    "safety": "fitness",
}

# When multiple owners are implicated by different failing checks in the same
# report, research is retried first: fitness's macro/workout numbers assume
# research's evidence and citations are already correct, so a research-owned
# fix may also resolve a downstream fitness-owned symptom, but never the
# reverse. See docs/reports/known_limitations_remediation_plan.md, L1, Phase 4.
_OWNER_RETRY_PRECEDENCE: tuple[str, ...] = ("research", "fitness")


def _determine_retry_target(checks: dict[str, dict[str, Any]]) -> str | None:
    """Which capability should be retried automatically, given which checks
    failed -- None when everything passed, or no failing check has a known
    owner (nothing to usefully retry)."""
    failing_owners: set[str] = set()
    for key, owner in _CHECK_OWNERS.items():
        check = checks.get(key)
        if check is None:
            continue
        check_passed = check["pass_fail"] if key == "ragas" else check["passed"]
        if not check_passed:
            failing_owners.add(owner)
    for owner in _OWNER_RETRY_PRECEDENCE:
        if owner in failing_owners:
            return owner
    return None


def build_verification_report_for_checks(checks: dict[str, dict[str, Any]]) -> dict[str, Any]:
    passed = True
    feedback_parts: list[str] = []
    for key, label in _REPORT_LABELS:
        check = checks.get(key)
        if check is None:
            continue
        if not check["passed"]:
            passed = False
        if check["issues"]:
            feedback_parts.append(f"{label} issues: {', '.join(check['issues'])}")

    ragas = checks.get("ragas")
    if ragas is not None:
        if not ragas["pass_fail"]:
            passed = False
            feedback_parts.append(
                f"Faithfulness score {ragas['faithfulness_score']} below "
                f"{FAITHFULNESS_PASS_THRESHOLD}"
            )

    return {
        **checks,
        "passed": passed,
        "feedback": "; ".join(feedback_parts) if feedback_parts else None,
        "retry_target": _determine_retry_target(checks) if not passed else None,
    }
