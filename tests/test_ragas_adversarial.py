"""L1 step 4: comparison methodology against the golden + adversarial fixtures.

See docs/reports/known_limitations_remediation_plan.md, L1 step 4, for the
measurable bar this implements: >=80% overall pass/fail agreement between the
heuristic and the real Ragas SDK, and zero missed false negatives on the
adversarial subset specifically (heuristic says pass, real Ragas says fail).
"""

import os
from pathlib import Path

import pytest

from core.evaluation.ragas_benchmark import (
    compare_faithfulness_scorers,
    load_adversarial_cases,
    load_golden_cases,
    run_golden_case,
)
from core.subgraphs.verification.utils import heuristic_faithfulness_data

ADVERSARIAL_FIXTURE = Path(__file__).resolve().parent / "fixtures" / "ragas_adversarial.json"
GOLDEN_FIXTURE = Path(__file__).resolve().parent / "fixtures" / "ragas_golden.json"

# Real Ragas SDK calls cost real tokens against a real judge LLM -- opt-in
# only, so the normal test suite never spends API quota. Run with:
#   RUN_REAL_RAGAS_COMPARISON=1 uv run pytest tests/test_ragas_adversarial.py -v
_RUN_REAL_COMPARISON = os.environ.get("RUN_REAL_RAGAS_COMPARISON") == "1"


def test_adversarial_fixture_loads() -> None:
    cases = load_adversarial_cases(ADVERSARIAL_FIXTURE)
    assert len(cases) >= 3
    for case in cases:
        assert case.draft_plan.strip()
        assert case.evidence
        assert case.planted_issue


def test_heuristic_blind_spot_on_adversarial_cases() -> None:
    """Documents the exact risk L1 exists to catch: the token-overlap heuristic
    currently passes every one of these hand-authored, deliberately unfaithful
    drafts, because it scores vocabulary overlap, not entailment. If this
    assertion ever starts failing, the heuristic's blind spot has narrowed --
    worth noting in the L1 write-up, not a bug in this test."""
    cases = load_adversarial_cases(ADVERSARIAL_FIXTURE)
    results = {
        case.case_id: heuristic_faithfulness_data(case.draft_plan, case.evidence) for case in cases
    }
    fooled = [case_id for case_id, result in results.items() if result["pass_fail"]]
    assert fooled == list(results.keys()), (
        f"Expected the heuristic to pass every adversarial case (that's the "
        f"blind spot L1 is about); it correctly failed: "
        f"{set(results) - set(fooled)}"
    )


@pytest.mark.skipif(
    not _RUN_REAL_COMPARISON,
    reason="Opt-in only: set RUN_REAL_RAGAS_COMPARISON=1 (real LLM judge calls, costs tokens)",
)
def test_real_ragas_agreement_bar_on_adversarial_cases(tmp_path: Path) -> None:
    cases = load_adversarial_cases(ADVERSARIAL_FIXTURE)
    comparison = compare_faithfulness_scorers(cases, include_real=True)

    assert comparison["summary"]["false_negative_rate"] == 0.0, (
        "Real Ragas must flag every case the adversarial fixture was built to "
        "be unfaithful -- a nonzero false-negative rate here means the "
        "heuristic is silently rubber-stamping unfaithful plans in practice, "
        "which is the strongest possible evidence for flipping "
        "verification_use_real_ragas in production (see L1 step 6)."
    )
    assert comparison["summary"]["agreement_rate"] >= 0.80


@pytest.mark.skipif(
    not _RUN_REAL_COMPARISON,
    reason="Opt-in only: set RUN_REAL_RAGAS_COMPARISON=1 (real LLM judge calls, costs tokens)",
)
def test_real_ragas_sanity_check_on_clean_golden_cases(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Near-100% agreement expected here -- these 3 cases are pipeline-generated
    and not adversarial, so this is a sanity check, not a finding (see L1 step
    4's note that agreement on easy cases alone doesn't validate the heuristic)."""
    from core.config.settings import get_settings

    monkeypatch.setattr(get_settings(), "verification_use_real_ragas", True)

    golden_cases = load_golden_cases(GOLDEN_FIXTURE)
    workspace_root = tmp_path / "ragas_workspace"
    disagreements = [
        result.case_id
        for case in golden_cases
        for result in [
            run_golden_case(case, workspace_root=workspace_root, run_id=f"sanity-{case.case_id}")
        ]
        if result.real_pass_fail is not None and result.real_pass_fail != result.pass_fail
    ]

    assert not disagreements, f"Unexpected disagreement on clean cases: {disagreements}"
