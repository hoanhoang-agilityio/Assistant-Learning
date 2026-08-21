"""Ragas evaluators for the ``search_knowledge`` retrieval path.

Ragas is an optional extra (``uv sync --extra evals``), imported only when the
observations scope actually runs — see ``evals/evaluators/__init__.py``. It
pulls its own LLM stack and is not a runtime need.

Reference-free metrics only. Production traces carry no ground-truth answers,
so anything named ``...WithReference`` or ``ContextRecall`` belongs in a
``run_experiment`` over a labelled Langfuse dataset, never here.

Ragas returns a bare float with no reasoning, which is a real loss against the
written judges. Each evaluator puts something diagnostic in ``comment`` — you
cannot act on an unexplained 0.3.
"""

from typing import Any

from langfuse import Evaluation
from openai import AsyncOpenAI
from ragas.dataset_schema import SingleTurnSample
from ragas.llms import llm_factory
from ragas.metrics import Faithfulness, LLMContextPrecisionWithoutReference

from app.core.configs.config import settings

# Faithfulness decomposes an answer into claims and verifies each, so it is
# several LLM calls per sample and the slowest thing in a run. Measured at ~120s
# for one 4.5KB answer against `gpt-5`, which is what this app's answers weigh,
# so the old 120s cap was landing on the wrong side of the coin flip.
SCORE_TIMEOUT_SECONDS = 300.0

# Ragas defaults to 1024, which a reasoning model spends on reasoning tokens
# before it emits a single character of the structured output — the run then
# dies on `IncompleteOutputException`, not on anything about the data. Ragas'
# own `_map_openai_params` documents 4096+ as the floor for the gpt-5 series,
# but that is sized for tutorial-length answers: decomposing a full training
# plan into claims needs far more, and 8192 still truncated on real traffic.
# The cap only bounds a spend that never happens on short answers, so it is set
# well clear of where truncation was observed. Ragas maps it to
# `max_completion_tokens` for us.
JUDGE_MAX_TOKENS = 16384

# `LangchainLLMWrapper` is deprecated in ragas 0.4 and warns pointing here.
_llm = llm_factory(
    settings.EVALUATION_LLM,
    client=AsyncOpenAI(
        api_key=settings.EVALUATION_API_KEY,
        base_url=settings.EVALUATION_BASE_URL,
    ),
    max_tokens=JUDGE_MAX_TOKENS,
)
_faithfulness = Faithfulness(llm=_llm)
_context_precision = LLMContextPrecisionWithoutReference(llm=_llm)


def _response_text(output: Any) -> str:
    """Extract a response string for ragas from a mapped output.

    The tool observation holds the retrieval, not the assistant's answer, so in
    practice the answer arrives through ``metadata["response"]``, which
    ``observation_mapper`` fills from the parent trace. This fallback only
    covers a caller that mapped a plain string into ``output``.

    Args:
        output: Whatever the mapper put in ``output``.

    Returns:
        The response text, or an empty string when there is none to score.
    """
    if isinstance(output, str):
        return output
    return ""


async def rag_faithfulness(*, input, output, expected_output=None, metadata=None, **kwargs: Any):
    """Score whether the answer is grounded in the retrieved passages.

    This is the metric that earns its keep here: it checks the answer stayed
    with the passages rather than inventing a citation, which is exactly what
    ``search_knowledge``'s own docstring warns against.

    Abstains when nothing was retrieved. Most turns in this app are plan
    build/verify turns with no retrieval at all, and scoring those would produce
    a stream of near-zero values that reads as a quality collapse.
    """
    meta = metadata or {}
    contexts = meta.get("contexts") or []
    response = meta.get("response") or _response_text(output)
    if not contexts or not response or not input:
        return []

    sample = SingleTurnSample(
        user_input=input,
        response=response,
        retrieved_contexts=contexts,
    )
    value = await _faithfulness.single_turn_ascore(sample, timeout=SCORE_TIMEOUT_SECONDS)
    return Evaluation(
        name="faithfulness",
        value=value,
        comment=f"{len(contexts)} passages: {', '.join(filter(None, meta.get('sources') or []))}",
    )


async def rag_context_precision(
    *, input, output, expected_output=None, metadata=None, **kwargs: Any
):
    """Score how much of what was retrieved was actually relevant.

    Uses the reference-free variant, so it needs no labelled answer. The score
    name is ``llm_context_precision_without_reference`` — ragas' own name for
    the metric, kept as-is so the Langfuse axis matches the class that produced
    it.
    """
    meta = metadata or {}
    contexts = meta.get("contexts") or []
    response = meta.get("response") or _response_text(output)
    if not contexts or not response or not input:
        return []

    sample = SingleTurnSample(
        user_input=input,
        response=response,
        retrieved_contexts=contexts,
    )
    value = await _context_precision.single_turn_ascore(sample, timeout=SCORE_TIMEOUT_SECONDS)
    return Evaluation(
        name=_context_precision.name,
        value=value,
        comment=f"{len(contexts)} passages retrieved",
    )


RAG_EVALUATORS = [rag_faithfulness, rag_context_precision]

__all__ = ["RAG_EVALUATORS", "rag_context_precision", "rag_faithfulness"]
