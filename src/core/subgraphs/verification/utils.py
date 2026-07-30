"""Backwards-compatible re-exports for the old verification.utils module.

This file used to hold the entire verification capability -- 448 lines of
citation, consistency, safety and faithfulness rules -- under a name that
signalled "nothing important here". The logic now lives in modules named after
what they do:

    checks/citation.py       what counts as a cited source
    checks/consistency.py    draft vs. computed macro/training numbers
    checks/safety.py         which flags and phrasings block delivery
    checks/faithfulness.py   heuristic + real-Ragas scoring, and the threshold
    context.py               loading a run's verification inputs from the VFS
    report.py                combining checks into one report + retry ownership
    artifacts.py             persisting results back to the VFS

Nothing was rewritten in the move. This shim exists so existing importers keep
working; prefer importing from the modules above in new code.
"""

from core.subgraphs.verification.artifacts import write_verification_artifacts
from core.subgraphs.verification.checks.citation import citation_check_data
from core.subgraphs.verification.checks.consistency import consistency_check_data
from core.subgraphs.verification.checks.faithfulness import (
    FAITHFULNESS_PASS_THRESHOLD,
    evaluate_faithfulness,
    heuristic_faithfulness_data,
    heuristic_faithfulness_score,
)
from core.subgraphs.verification.checks.safety import (
    CRITICAL_SAFETY_FLAGS,
    safety_check_data,
)
from core.subgraphs.verification.context import load_verification_context
from core.subgraphs.verification.report import build_verification_report_for_checks

__all__ = [
    "CRITICAL_SAFETY_FLAGS",
    "FAITHFULNESS_PASS_THRESHOLD",
    "build_verification_report_for_checks",
    "citation_check_data",
    "consistency_check_data",
    "evaluate_faithfulness",
    "heuristic_faithfulness_data",
    "heuristic_faithfulness_score",
    "load_verification_context",
    "safety_check_data",
    "write_verification_artifacts",
]
