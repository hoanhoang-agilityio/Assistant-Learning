"""L1 Phase 4: verification's owner-attribution ("who should fix this failure")
feeding the Policy Engine's automatic retry rule (see tests/test_supervisor_router.py
for the routing side). citation/faithfulness are research-owned; consistency/safety
are fitness-owned; research is retried first when both are implicated (fitness's
numbers assume research's evidence/citations are already correct)."""

from core.subgraphs.verification.utils import build_verification_report_for_checks


def _check(passed: bool, issues: list[str] | None = None) -> dict:
    return {"passed": passed, "issues": issues or []}


def _ragas(pass_fail: bool, score: float = 0.5) -> dict:
    return {"faithfulness_score": score, "pass_fail": pass_fail}


def test_all_checks_passing_has_no_retry_target() -> None:
    report = build_verification_report_for_checks(
        {
            "citation": _check(True),
            "consistency": _check(True),
            "safety": _check(True),
            "ragas": _ragas(True, 0.95),
        }
    )
    assert report["passed"] is True
    assert report["retry_target"] is None


def test_citation_failure_targets_research() -> None:
    report = build_verification_report_for_checks(
        {
            "citation": _check(False, ["no_sources_referenced_in_draft"]),
            "consistency": _check(True),
            "safety": _check(True),
            "ragas": _ragas(True, 0.95),
        }
    )
    assert report["passed"] is False
    assert report["retry_target"] == "research"


def test_faithfulness_failure_targets_research() -> None:
    report = build_verification_report_for_checks(
        {
            "citation": _check(True),
            "consistency": _check(True),
            "safety": _check(True),
            "ragas": _ragas(False, 0.42),
        }
    )
    assert report["passed"] is False
    assert report["retry_target"] == "research"


def test_safety_failure_targets_fitness() -> None:
    report = build_verification_report_for_checks(
        {
            "citation": _check(True),
            "consistency": _check(True),
            "safety": _check(False, ["aggressive_calorie_deficit"]),
            "ragas": _ragas(True, 0.95),
        }
    )
    assert report["passed"] is False
    assert report["retry_target"] == "fitness"


def test_consistency_failure_targets_fitness() -> None:
    report = build_verification_report_for_checks(
        {
            "citation": _check(True),
            "consistency": _check(False, ["draft_missing_calorie_target"]),
            "safety": _check(True),
            "ragas": _ragas(True, 0.95),
        }
    )
    assert report["passed"] is False
    assert report["retry_target"] == "fitness"


def test_research_owned_failure_takes_precedence_over_fitness_owned() -> None:
    """Both a research-owned (citation) and a fitness-owned (safety) check fail
    at once -- research is retried first: fixing research's evidence/citations
    may also resolve the downstream fitness symptom, never the reverse."""
    report = build_verification_report_for_checks(
        {
            "citation": _check(False, ["no_sources_referenced_in_draft"]),
            "consistency": _check(True),
            "safety": _check(False, ["aggressive_calorie_deficit"]),
            "ragas": _ragas(True, 0.95),
        }
    )
    assert report["passed"] is False
    assert report["retry_target"] == "research"


def test_missing_check_is_treated_as_not_failing() -> None:
    """A check the caller didn't request at all (e.g. faithfulness skipped) must
    not be treated as a failure with no owner -- only checks actually present
    and failing count toward retry_target."""
    report = build_verification_report_for_checks(
        {
            "consistency": _check(True),
            "safety": _check(False, ["aggressive_calorie_deficit"]),
        }
    )
    assert report["passed"] is False
    assert report["retry_target"] == "fitness"
