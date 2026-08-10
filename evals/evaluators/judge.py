"""The shared LLM-judge call every prompt-based metric goes through."""

from pathlib import Path

from openai import AsyncOpenAI
from pydantic import BaseModel, Field
from tenacity import retry, retry_if_exception_type, stop_after_attempt, wait_exponential

from app.core.configs.config import settings
from app.services.llm.service import RETRYABLE_ERRORS

PROMPTS_DIR = Path(__file__).parent.parent / "prompts"

_prompt_cache: dict[str, str] = {}

# Deliberately not the app's own model. `EVALUATION_LLM` defaults to `gpt-5`
# against `DEFAULT_LLM_MODEL`'s `gpt-5-mini`: a model judging its own output
# grades itself generously.
_client = AsyncOpenAI(
    api_key=settings.EVALUATION_API_KEY,
    base_url=settings.EVALUATION_BASE_URL,
)


class ScoreSchema(BaseModel):
    """One judge verdict, forced as the reply's ``response_format``."""

    score: float = Field(description="provide a score between 0 and 1")
    reasoning: str = Field(description="provide a one sentence reasoning")


def load_prompt(name: str) -> str:
    """Read a metric's prompt file, caching it for the run.

    Args:
        name: The metric name, which is also the filename stem and the Langfuse
            score name.

    Returns:
        The file's contents — the judge's entire system prompt.
    """
    if name not in _prompt_cache:
        _prompt_cache[name] = (PROMPTS_DIR / f"{name}.md").read_text(encoding="utf-8")
    return _prompt_cache[name]


@retry(
    stop=stop_after_attempt(3),
    wait=wait_exponential(multiplier=1, min=4, max=10),
    # The same tuple the LLM service retries on, so the two cannot come to
    # disagree about which failures are worth another attempt.
    retry=retry_if_exception_type(RETRYABLE_ERRORS),
    reraise=True,
)
async def llm_judge(prompt: str, input_text: str, output_text: str) -> ScoreSchema:
    """Score one generation against one metric prompt.

    Args:
        prompt: The metric's system prompt.
        input_text: The formatted conversation up to the last message.
        output_text: The formatted last message.

    Returns:
        The judge's verdict.

    Raises:
        ValueError: When the model returned no parsed output. Raising rather
            than returning ``None`` is deliberate — the batch runner logs a
            raising evaluator and moves on, so the failure lands in the
            evaluator stats instead of being averaged in as a score.
    """
    response = await _client.chat.completions.parse(
        model=settings.EVALUATION_LLM,
        messages=[
            {"role": "system", "content": prompt},
            {"role": "user", "content": f"Input: {input_text}\nGeneration: {output_text}"},
        ],
        response_format=ScoreSchema,
    )
    parsed = response.choices[0].message.parsed
    if parsed is None:
        raise ValueError("judge_returned_no_parsed_output")
    return parsed


__all__ = ["PROMPTS_DIR", "ScoreSchema", "llm_judge", "load_prompt"]
