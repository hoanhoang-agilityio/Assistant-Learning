"""Turning a pasted plan into structure, before any agent gets a say.

This used to be a tool argument: the review agent read the user's message and
passed its reading to ``score_plan``. Two things were wrong with that, and only
the second is about correctness.

The first is that the agent could get the shape wrong, and did — a wrong guess
at the nesting arrived as an empty transcription, which the tool reported as
"nothing plan-shaped was found", which the supervisor relayed as "please paste
your plan again". Re-pasting could not fix a fault on the model's side of the
call, so the turn had no exit.

The second is that reading the user's message was never a decision the agent
should have been able to skip. It could answer without calling ``score_plan``
at all, and when it did, it wrote the review from its own knowledge — no rubric,
no macros, no injury check, and no way for the answer to look any different. A
mandatory step offered as a tool is a mandatory step the model can decline
(``docs/workflow.md`` §5).

So transcription is a plain function with a structured-output call in it, run
before the agent is invoked, exactly as the topic gate and ``extract_profile``
are. What reaches the agent is already read.
"""

from pathlib import Path

from langchain_core.messages import HumanMessage

from app.core.logging import logger
from app.schemas.graph import PastedDay, PastedPlan
from app.services.llm.service import llm_service

_TRANSCRIBE_TEMPLATE = (Path(__file__).parent / "prompts" / "transcribe.md").read_text(
    encoding="utf-8"
)

# Reading text into a fixed schema is the cheapest thing a model does here, and
# the schema is what carries the correctness. The classifier uses the same one.
_TRANSCRIBER_MODEL = "gpt-5-mini"


def load_transcribe_prompt(pasted: str) -> str:
    """Render the transcription prompt.

    Args:
        pasted: The user's message, as they sent it.

    Returns:
        The formatted prompt.
    """
    return _TRANSCRIBE_TEMPLATE.format(pasted=pasted)


async def transcribe(pasted: str) -> list[PastedDay]:
    """Read a pasted plan into days and exercise lines.

    Args:
        pasted: The user's message, as they sent it.

    Returns:
        One entry per training day, empty when the message holds no plan. A
        failed call also returns empty: the caller's next move — telling the
        user no plan could be read — is the same either way, and it is a better
        answer than an assessment of half a plan.
    """
    try:
        transcribed: PastedPlan = await llm_service.call(
            [HumanMessage(content=load_transcribe_prompt(pasted))],
            model_name=_TRANSCRIBER_MODEL,
            response_format=PastedPlan,
        )
    except Exception as error:
        logger.exception("review_transcription_failed", error=str(error))
        return []

    days = [day for day in transcribed.days if day.exercises]

    return days


__all__ = ["load_transcribe_prompt", "transcribe"]
