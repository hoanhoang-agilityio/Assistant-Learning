"""Real Ragas SDK faithfulness scoring.

Kept out of core.subgraphs.verification (production's verification path,
which costs zero LLM tokens today) deliberately: importing this module pulls
in the ragas/datasets import graph, and nothing in verification/graph.py or
verification/utils.py imports it. It is wired only into
core.evaluation.ragas_benchmark.evaluate_draft_faithfulness, gated behind
settings.verification_use_real_ragas. See
docs/reports/known_limitations_remediation_plan.md, L1, for the staged plan
this implements (steps 1-3; step 6 covers what a future production flip
would additionally need).
"""

from __future__ import annotations

from typing import Any

from langchain_core.language_models.chat_models import BaseChatModel
from ragas import evaluate
from ragas.dataset_schema import EvaluationDataset
from ragas.llms import LangchainLLMWrapper
from ragas.metrics import faithfulness

from core.subgraphs.verification.utils import FAITHFULNESS_PASS_THRESHOLD


def ragas_faithfulness_data(
    draft_plan: str,
    evidence: list[dict[str, Any]],
    *,
    query: str,
    judge_llm: BaseChatModel,
) -> dict[str, Any]:
    """Score draft_plan's faithfulness to evidence via Ragas's faithfulness metric.

    Issues two sequential LLM calls through judge_llm (statement generation,
    then NLI verdicts against retrieved_contexts) -- pass
    core.llm.factory.get_standard_llm() unless a node-specific reasoning
    override is needed. Mirrors
    core.subgraphs.verification.utils.heuristic_faithfulness_data's return
    shape so callers don't need to branch on which scorer produced it.
    """
    retrieved_contexts = [str(item.get("content", "")) for item in evidence if item.get("content")]
    dataset = EvaluationDataset.from_list(
        [
            {
                "user_input": query,
                "response": draft_plan,
                "retrieved_contexts": retrieved_contexts,
            }
        ]
    )
    result = evaluate(
        dataset,
        metrics=[faithfulness],
        llm=LangchainLLMWrapper(judge_llm),
        show_progress=False,
    )
    score = float(result["faithfulness"][0])
    return {
        "faithfulness_score": score,
        "pass_fail": score >= FAITHFULNESS_PASS_THRESHOLD,
        "method": "ragas_sdk_faithfulness",
        "threshold": FAITHFULNESS_PASS_THRESHOLD,
    }
