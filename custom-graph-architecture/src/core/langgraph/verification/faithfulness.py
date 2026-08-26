"""The RAGAS gate: how much of a QA answer the passages it retrieved actually carry.

RAGAS 0.4.3 imports ``langchain_community.chat_models.vertexai`` at package import time,
and langchain-community dropped that module in 0.4 — the version this project's
langchain-core 1.x pins. The module is read for one ``isinstance`` list of models that
support n-completions, so a placeholder stands in for it; nothing here goes near Vertex AI.
"""

import importlib
import sys
import types
from functools import lru_cache
from math import isnan
from typing import TYPE_CHECKING, Any

from openai import AsyncOpenAI

from src.core.configs.config import settings
from src.schemas import RetrievedChunk
from src.utils.logging import logger

if TYPE_CHECKING:
    from ragas.metrics.collections.faithfulness import Faithfulness

VERTEXAI_MODULE = "langchain_community.chat_models.vertexai"


def install_vertexai_stub() -> None:
    """Stand a placeholder in for the module RAGAS imports and langchain-community dropped."""

    try:
        importlib.import_module(VERTEXAI_MODULE)
    except ImportError:
        module = types.ModuleType(VERTEXAI_MODULE)
        module.ChatVertexAI = type("ChatVertexAI", (), {})
        sys.modules[VERTEXAI_MODULE] = module


@lru_cache
def build_faithfulness_metric() -> "Faithfulness":
    """Build the RAGAS faithfulness metric once, on its own structured-output client."""

    install_vertexai_stub()

    from ragas.llms import llm_factory  # noqa: PLC0415
    from ragas.metrics.collections.faithfulness import Faithfulness  # noqa: PLC0415

    return Faithfulness(
        llm=llm_factory(
            settings.DEFAULT_LLM_MODEL,
            client=AsyncOpenAI(api_key=settings.OPENAI_API_KEY),
            max_tokens=settings.RAGAS_MAX_TOKENS,
        )
    )


def _score_value(result: Any) -> float | None:
    """Read a metric result as a score, or nothing when RAGAS found no statement to judge."""

    score = float(result.value)
    return None if isnan(score) else score


async def score_faithfulness(
    *,
    question: str,
    answer: str | None,
    passages: list[RetrievedChunk],
) -> float | None:
    """Score an answer against the passages it was written from, or nothing if unscorable."""

    if not question or not answer or not passages:
        return None

    try:
        result = await build_faithfulness_metric().ascore(
            user_input=question,
            response=answer,
            retrieved_contexts=[passage["text"] for passage in passages],
        )
    except Exception as error:
        logger.exception("faithfulness_scoring_failed", error=str(error))
        return None

    return _score_value(result)
