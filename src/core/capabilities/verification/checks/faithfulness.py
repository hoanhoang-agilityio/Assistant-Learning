"""Faithfulness scoring: the heuristic proxy, the real-Ragas path, and the
single dispatch point between them.

FAITHFULNESS_PASS_THRESHOLD lives here because this is the check that owns it.
"""

import logging
import re
from typing import Any

from core.config.settings import get_settings

logger = logging.getLogger(__name__)

FAITHFULNESS_PASS_THRESHOLD = 0.90


def heuristic_faithfulness_score(draft_plan: str, evidence: list[dict[str, Any]]) -> float:
    """Zero-cost, zero-latency evidence-grounding proxy (token overlap, not entailment).

    Deliberately not Ragas-backed -- see core.evaluation.ragas for the real
    Ragas SDK faithfulness scorer, gated behind
    settings.verification_use_real_ragas and wired only into the benchmark
    script so far (docs/reports/known_limitations_remediation_plan.md, L1).

    Callers should pass grounded_claims text (not the full final_plan) so
    engine-authored macros/training sections are not scored as research claims.
    """
    if not draft_plan.strip():
        return 0.0
    if not evidence:
        return 0.5

    evidence_text = " ".join(
        str(item.get("content", "")) + " " + str(item.get("url", "")) for item in evidence
    ).lower()
    draft_lower = draft_plan.lower()
    evidence_tokens = {token for token in re.findall(r"[a-z]{5,}", evidence_text)}
    if not evidence_tokens:
        return 0.6

    matched_tokens = sum(1 for token in evidence_tokens if token in draft_lower)
    overlap_ratio = matched_tokens / len(evidence_tokens)
    grounded_sections = sum(
        1
        for marker in (
            "macro targets",
            "training plan",
            "evidence summary",
            "evidence applied",
            "grounded claims",
            "source:",
        )
        if marker in draft_lower
    )
    section_bonus = min(grounded_sections * 0.08, 0.24)
    score = min(0.65 + overlap_ratio * 0.25 + section_bonus, 1.0)
    return round(score, 2)


def heuristic_faithfulness_data(draft_plan: str, evidence: list[dict[str, Any]]) -> dict[str, Any]:
    """Faithfulness result shaped like core.evaluation.ragas.ragas_faithfulness_data's
    output, but scored by the heuristic above, not the real Ragas SDK."""
    score = heuristic_faithfulness_score(draft_plan, evidence)
    pass_fail = score >= FAITHFULNESS_PASS_THRESHOLD
    return {
        "faithfulness_score": score,
        "pass_fail": pass_fail,
        "method": "heuristic_evidence_grounding",
        "threshold": FAITHFULNESS_PASS_THRESHOLD,
        "answer_relevancy_score": None,
        "context_precision_score": None,
        "context_recall_score": None,
        "answer_correctness_score": None,
    }


def evaluate_faithfulness(
    draft_plan: str,
    evidence: list[dict[str, Any]],
    *,
    query: str = "",
    reference: str | None = None,
    use_real: bool,
) -> dict[str, Any]:
    """Single dispatch point for faithfulness scoring -- heuristic or real Ragas SDK,
    chosen by the explicit `use_real` the caller passes in (this function never reads
    settings itself; production and the benchmark each decide their own gating).

    Callers: verification/executor.py (production, gated behind
    settings.verification_production_use_real_ragas, off by default) and
    core/evaluation/ragas_benchmark.py (benchmark, passes
    settings.verification_use_real_ragas). Having one function means the two
    call sites can no longer silently drift into different dispatch logic over time
    (2026-07-30 Phase 1 remediation -- see docs/reports/known_limitations_remediation_plan.md, L1).

    When use_real is True, heuristic_faithfulness_data is the fallback on ANY
    failure in the real path -- rate limit already exceeded, the OpenAI call
    itself failing, or a Ragas SDK error (2026-07-30 Phase 3: "heuristic becomes
    the fallback", not a second gate to configure). A live user-facing request
    must never fail outright because the real judge call hit a transient
    problem; degrading to the free heuristic for that one call is safer than
    blocking plan delivery.
    """
    if use_real:
        try:
            return _evaluate_faithfulness_real(
                draft_plan, evidence, query=query, reference=reference
            )
        except Exception:
            logger.exception(
                "Real Ragas faithfulness scoring failed; falling back to the "
                "heuristic proxy for this call."
            )
    return heuristic_faithfulness_data(draft_plan, evidence)


def _evaluate_faithfulness_real(
    draft_plan: str,
    evidence: list[dict[str, Any]],
    *,
    query: str,
    reference: str | None,
) -> dict[str, Any]:
    """The use_real=True path, split out so evaluate_faithfulness's try/except
    covers every failure mode uniformly (rate limit, API error, SDK error).

    The `ragas` SDK import graph is heavy (pulls in `datasets`/pandas/its own
    LLM-wrapper stack) -- deferred here (not a module-level import) so
    importing this module, or calling evaluate_faithfulness with
    use_real=False, never pays that cost.

    Real Ragas calls the judge LLM through its own internal harness, not this
    repo's core.llm.factory wrappers -- so unlike every other LLM call in this
    codebase, it would otherwise be invisible to the per-user rate limiter and
    to token_cost.md. get_openai_callback() captures the real token usage so
    it can be checked/recorded through the same AIRateLimiter every other call
    goes through (get_rate_limit_user_id() is the same context var
    record_active_user_response() reads elsewhere in this codebase).
    """
    from langchain_community.callbacks import get_openai_callback

    from core.evaluation.ragas import ragas_faithfulness_data
    from core.llm.factory import get_rate_limiter, get_standard_llm
    from core.rate_limit.context import get_rate_limit_user_id

    settings = get_settings()
    rate_limiter = get_rate_limiter()
    user_id = get_rate_limit_user_id()
    rate_limiter.check_active_user_tokens()

    with get_openai_callback() as callback:
        result = ragas_faithfulness_data(
            draft_plan,
            evidence,
            query=query,
            judge_llm=get_standard_llm(),
            reference=reference,
        )
    rate_limiter.record_usage(
        user_id,
        input_tokens=callback.prompt_tokens,
        output_tokens=callback.completion_tokens,
        model_name=settings.openai_standard_model,
    )
    return result
