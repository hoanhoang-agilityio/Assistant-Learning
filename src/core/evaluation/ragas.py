"""Real Ragas SDK multi-metric scoring.

Not imported at module level by verification/utils.py or verification/executor.py
(the ragas/datasets import graph is heavy) -- verification.utils.evaluate_faithfulness
imports this module lazily, only inside its `use_real` branch, so the heuristic-only
path (still production's default -- see executor.py's verification_production_use_real_ragas
gate, off unless a deploy explicitly opts in) never pays that cost. Also used directly
by core.evaluation.ragas_benchmark for offline comparison. See
docs/reports/known_limitations_remediation_plan.md, L1, for the staged plan this
implements; the production-flip option (this module's L1 step 6) now exists behind
that settings flag, with the real judge call wrapped in a heuristic fallback on any
failure -- see evaluate_faithfulness's docstring.

Metrics:
  Always (no ground truth needed):
    - faithfulness — response grounded in retrieved_contexts
    - answer_relevancy — response relevant to user_input (needs embeddings)
    - context_precision — retrieval precision via LLMContextPrecisionWithoutReference
  When ``reference`` (ground-truth answer) is provided:
    - context_precision — with-reference variant (replaces the without-ref one)
    - context_recall — retrieval recall vs reference
    - answer_correctness — response vs reference

Callers should pass grounded_claims text as ``draft_plan`` / response so
engine-authored macros and training prescriptions are not scored as research
claims.
"""

from __future__ import annotations

import math
import os
from typing import Any

# Must be set before ragas's own module (imported below) ever calls
# evaluate() -- ragas/_analytics.py reads this env var fresh on each
# telemetry attempt, not once at import time, but setting it before the
# import is simplest and safest. Ragas phones home to its own analytics
# endpoint (t.explodinggradients.com) on every evaluate() call; in a
# network-restricted environment this can retry indefinitely instead of
# failing fast (observed: ~470 consecutive retries during this repo's Phase 0
# benchmark runs, hanging the process for minutes). A long-running production
# process making many real-Ragas calls over its lifetime is exactly the shape
# that risks hitting this, independent of any one sandbox's specific network
# restrictions -- disable it unconditionally rather than only where it was
# first observed. RAGAS_DO_NOT_TRACK is Ragas's own documented opt-out.
os.environ.setdefault("RAGAS_DO_NOT_TRACK", "true")

from langchain_core.embeddings import Embeddings  # noqa: E402
from langchain_core.language_models.chat_models import BaseChatModel  # noqa: E402
from langchain_openai import OpenAIEmbeddings  # noqa: E402
from ragas import evaluate  # noqa: E402
from ragas.dataset_schema import EvaluationDataset  # noqa: E402
from ragas.llms import LangchainLLMWrapper  # noqa: E402
from ragas.metrics import (  # noqa: E402
    LLMContextPrecisionWithoutReference,
    answer_correctness,
    answer_relevancy,
    context_precision,
    context_recall,
    faithfulness,
)
from ragas.metrics.base import Metric  # noqa: E402

from core.capabilities.verification.utils import FAITHFULNESS_PASS_THRESHOLD  # noqa: E402
from core.config.settings import get_settings  # noqa: E402

_ALWAYS_METRICS: list[Metric] = [
    faithfulness,
    answer_relevancy,
    LLMContextPrecisionWithoutReference(),
]
_REFERENCE_METRICS: list[Metric] = [
    context_precision,
    context_recall,
    answer_correctness,
]


def _score_or_none(raw: Any) -> float | None:
    if raw is None:
        return None
    try:
        score = float(raw)
    except (TypeError, ValueError):
        return None
    if math.isnan(score):
        return None
    return score


def _result_score(result: Any, column: str) -> float | None:
    try:
        return _score_or_none(result[column][0])
    except (KeyError, IndexError, TypeError):
        return None


def _default_embeddings() -> Embeddings:
    settings = get_settings()
    return OpenAIEmbeddings(api_key=settings.openai_api_key)


def ragas_faithfulness_data(
    draft_plan: str,
    evidence: list[dict[str, Any]],
    *,
    query: str,
    judge_llm: BaseChatModel,
    reference: str | None = None,
    embeddings: Embeddings | None = None,
) -> dict[str, Any]:
    """Score draft_plan with Ragas faithfulness plus relevancy / retrieval / correctness.

    Always runs faithfulness, answer_relevancy, and context precision
    (without-reference). When ``reference`` is set, also runs with-reference
    context_precision, context_recall, and answer_correctness.

    ``pass_fail`` remains faithfulness-gated (threshold
    FAITHFULNESS_PASS_THRESHOLD) so callers that only consume the legacy
    shape stay compatible. Additional scores live alongside as optional
    ``*_score`` fields.
    """
    retrieved_contexts = [str(item.get("content", "")) for item in evidence if item.get("content")]
    row: dict[str, Any] = {
        "user_input": query,
        "response": draft_plan,
        "retrieved_contexts": retrieved_contexts,
    }
    metrics: list[Metric] = list(_ALWAYS_METRICS)
    if reference is not None and reference.strip():
        row["reference"] = reference
        # Prefer with-reference precision when GT is available.
        metrics = [faithfulness, answer_relevancy, *_REFERENCE_METRICS]

    dataset = EvaluationDataset.from_list([row])
    result = evaluate(
        dataset,
        metrics=metrics,
        llm=LangchainLLMWrapper(judge_llm),
        embeddings=embeddings or _default_embeddings(),
        show_progress=False,
    )

    faithfulness_score = _result_score(result, "faithfulness")
    if faithfulness_score is None:
        faithfulness_score = 0.0

    answer_relevancy_score = _result_score(result, "answer_relevancy")
    if reference is not None and reference.strip():
        context_precision_score = _result_score(result, "context_precision")
        context_recall_score = _result_score(result, "context_recall")
        answer_correctness_score = _result_score(result, "answer_correctness")
        method = "ragas_sdk_multi_metric_with_reference"
    else:
        context_precision_score = _result_score(result, "llm_context_precision_without_reference")
        context_recall_score = None
        answer_correctness_score = None
        method = "ragas_sdk_multi_metric"

    return {
        "faithfulness_score": faithfulness_score,
        "pass_fail": faithfulness_score >= FAITHFULNESS_PASS_THRESHOLD,
        "method": method,
        "threshold": FAITHFULNESS_PASS_THRESHOLD,
        "answer_relevancy_score": answer_relevancy_score,
        "context_precision_score": context_precision_score,
        "context_recall_score": context_recall_score,
        "answer_correctness_score": answer_correctness_score,
    }
