"""Real Ragas SDK multi-metric scoring (benchmark / eval only).

Kept out of core.subgraphs.verification (production's verification path,
which costs zero LLM tokens today) deliberately: importing this module pulls
in the ragas/datasets import graph, and nothing in verification/graph.py or
verification/utils.py imports it. It is wired only into
core.evaluation.ragas_benchmark.evaluate_draft_faithfulness, gated behind
settings.verification_use_real_ragas. See
docs/reports/known_limitations_remediation_plan.md, L1, for the staged plan
this implements (steps 1-3; step 6 covers what a future production flip
would additionally need).

Metrics:
  Always (no ground truth needed):
    - faithfulness — response grounded in retrieved_contexts
    - answer_relevancy — response relevant to user_input (needs embeddings)
    - context_precision — retrieval precision via LLMContextPrecisionWithoutReference
  When ``reference`` (ground-truth answer) is provided:
    - context_precision — with-reference variant (replaces the without-ref one)
    - context_recall — retrieval recall vs reference
    - answer_correctness — response vs reference
"""

from __future__ import annotations

import math
from typing import Any

from langchain_core.embeddings import Embeddings
from langchain_core.language_models.chat_models import BaseChatModel
from langchain_openai import OpenAIEmbeddings
from ragas import evaluate
from ragas.dataset_schema import EvaluationDataset
from ragas.llms import LangchainLLMWrapper
from ragas.metrics import (
    LLMContextPrecisionWithoutReference,
    answer_correctness,
    answer_relevancy,
    context_precision,
    context_recall,
    faithfulness,
)
from ragas.metrics.base import Metric

from core.config.settings import get_settings
from core.subgraphs.verification.utils import FAITHFULNESS_PASS_THRESHOLD

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
