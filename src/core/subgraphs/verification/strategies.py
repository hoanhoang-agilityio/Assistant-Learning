"""Verification strategy registry: which validators run, in what order, per workflow.

Phase 5 of the intent-aware orchestration refactor (see docs/reports/execution_plan_refactor/).
Replaces Verification's previously-unconditional 4-check chain with a strategy-driven
validator list -- adding a future strategy is a new registry entry, not new graph wiring.
Each `ValidatorStep` wraps one of the four existing check functions in
`verification/utils.py` unchanged; none of those functions themselves change.
"""

import json
from collections.abc import Callable
from pathlib import Path
from typing import Any, NamedTuple

from core.subgraphs.verification.utils import (
    citation_check_data,
    consistency_check_data,
    heuristic_faithfulness_data,
    safety_check_data,
)
from core.vfs import VFS
from core.vfs.layout import VERIFY_REPORT


class ValidatorStep(NamedTuple):
    """One named validator in a verification strategy's ordered list.

    `node_name` is also this phase's graph node name and the string that appears in
    `invoke_verification_subgraph`'s observability `steps` list -- kept identical to the
    pre-Phase-5 node names ("citation_check", etc.) so nothing that reads `steps` observes
    a change for the FULL strategy. `report_key` is the key this validator's result is
    stored under in `verification_report` (unchanged from today's report shape).
    """

    node_name: str
    report_key: str
    run: Callable[[dict[str, Any]], dict[str, Any]]


def _run_citation(state: dict[str, Any]) -> dict[str, Any]:
    return citation_check_data(state["draft_plan"], state["sources"])


def _run_consistency(state: dict[str, Any]) -> dict[str, Any]:
    return consistency_check_data(
        state["draft_plan"],
        state["macro_targets"],
        state["training_plan"],
        state["plan_blueprint"],
    )


def _run_safety(state: dict[str, Any]) -> dict[str, Any]:
    return safety_check_data(
        state["draft_plan"],
        state["safety_flags"],
        fitness_safety_passed=state.get("fitness_safety_passed"),
    )


def _run_faithfulness(state: dict[str, Any]) -> dict[str, Any]:
    return heuristic_faithfulness_data(state["draft_plan"], state["evidence"])


def _load_prior_report(workspace_path: str) -> dict[str, Any] | None:
    vfs = VFS.for_run(Path(workspace_path))
    if not vfs.exists(VERIFY_REPORT):
        return None
    return json.loads(vfs.read(VERIFY_REPORT))


def _carry_forward(
    report_key: str, missing_issue: str
) -> Callable[[dict[str, Any]], dict[str, Any]]:
    """Build a ValidatorStep.run function that copies `report_key` from the prior run's
    verification report instead of recomputing it (Phase 6: EDIT_REVIEW carries forward
    citation/faithfulness since Research isn't rerun for an edit). `resolve_strategy`'s F8
    fallback already guarantees a prior report exists whenever this runs, in the graph --
    the `missing_issue` fallback here is a defensive guard, not the primary mechanism."""

    def _run(state: dict[str, Any]) -> dict[str, Any]:
        prior = _load_prior_report(state["workspace_path"])
        if prior is not None and report_key in prior:
            return prior[report_key]
        if report_key == "ragas":
            return {
                "pass_fail": False,
                "faithfulness_score": 0.0,
                "method": "carry_forward_missing",
                "threshold": 0.0,
                "answer_relevancy_score": None,
                "context_precision_score": None,
                "context_recall_score": None,
                "answer_correctness_score": None,
            }
        return {"passed": False, "issues": [missing_issue]}

    return _run


CITATION = ValidatorStep("citation_check", "citation", _run_citation)
CONSISTENCY = ValidatorStep("consistency_check", "consistency", _run_consistency)
SAFETY = ValidatorStep("safety_check", "safety", _run_safety)
FAITHFULNESS = ValidatorStep("ragas_faithfulness", "ragas", _run_faithfulness)
CARRIED_CITATION = ValidatorStep(
    "citation_carry_forward", "citation", _carry_forward("citation", "no_prior_citation_report")
)
CARRIED_FAITHFULNESS = ValidatorStep(
    "faithfulness_carry_forward", "ragas", _carry_forward("ragas", "no_prior_faithfulness_report")
)

ALL_VALIDATOR_STEPS: tuple[ValidatorStep, ...] = (
    CITATION,
    CONSISTENCY,
    SAFETY,
    FAITHFULNESS,
    CARRIED_CITATION,
    CARRIED_FAITHFULNESS,
)

VERIFICATION_STRATEGIES: dict[str, list[ValidatorStep]] = {
    "FULL": [CITATION, CONSISTENCY, SAFETY, FAITHFULNESS],
    # citation/faithfulness need Research artifacts (sources.json/findings.json) that
    # never exist for a submitted external plan -- design-doc Sec5.5.
    "EXTERNAL_PLAN": [CONSISTENCY, SAFETY],
    # Phase 6: an edit only ever touches Fitness's output, never Research's -- consistency
    # and safety are freshly recomputed against the edited structured_workout, while
    # citation and faithfulness are carried forward from the prior verification report
    # rather than recomputed against Research artifacts that were never regenerated for
    # this edit. Deliberately uniform across every EditOperation type (ADD_DAY,
    # REPLACE_EXERCISE, etc.) rather than scoped per-operation -- the design docs left the
    # exact per-operation scoping open, and always refreshing the cheap, Fitness-derived
    # checks while always carrying forward the expensive, Research-derived ones is the
    # simplest interpretation that satisfies "don't recompute what Research didn't rerun."
    "EDIT_REVIEW": [CONSISTENCY, SAFETY, CARRIED_CITATION, CARRIED_FAITHFULNESS],
}


def resolve_strategy(
    verification_strategy: str | None,
    workspace_path: str | None = None,
) -> list[ValidatorStep]:
    """`FULL` is the default for any run without an explicit strategy (legacy/pre-Phase-5
    checkpoints, or a plan absent entirely) -- reproduces today's only behavior exactly.

    `workspace_path` (Phase 6, design review F8): when given and `verification_strategy`
    is `EDIT_REVIEW`, checks whether a prior verification report actually exists to carry
    forward from -- e.g. a plan's first-ever edit, or a report written under a retired
    strategy shape. If none exists, falls back to running `FULL`'s complete validator list
    once instead of carrying forward from nothing. Callers that don't need this fallback
    (e.g. `persist_trigger_data`, which only cares whether *some* faithfulness check is
    part of the strategy, carried-forward or not) may omit `workspace_path`.
    """
    strategy = verification_strategy or "FULL"
    if strategy == "EDIT_REVIEW" and workspace_path is not None:
        if _load_prior_report(workspace_path) is None:
            return VERIFICATION_STRATEGIES["FULL"]
    return VERIFICATION_STRATEGIES[strategy]
