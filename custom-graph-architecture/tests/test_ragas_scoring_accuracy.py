"""Integration checks that the real RAGAS judge separates a grounded answer from a made-up one.

Everything else about the gate is tested against a stubbed metric, which would keep passing
if the judge itself never ran — RAGAS defaults to a token budget a reasoning model spends
on reasoning alone, and a truncated verdict scores nothing at all. This is the test that
catches that, so it calls the model for real.
"""

import pytest

from src.configs.config import settings
from src.schemas import RetrievedChunk
from src.verification import score_faithfulness

QUESTION = "How much protein maximises training adaptation?"

PASSAGES: list[RetrievedChunk] = [
    {
        "text": (
            "Protein intake of 1.6 g/kg/day maximises training adaptation in "
            "resistance-trained lifters. Intakes above 2.2 g/kg/day show no further benefit."
        ),
        "source": "nutrition.docx",
        "score": 0.82,
    }
]

GROUNDED_ANSWER = (
    "Protein intake of 1.6 g/kg/day maximises training adaptation in resistance-trained "
    "lifters, and going above 2.2 g/kg/day adds no further benefit."
)

INVENTED_ANSWER = (
    "You need 4 g/kg of protein daily, plus 10 g of creatine and a 1974 NASA-designed "
    "carb cycle."
)


@pytest.mark.integration
async def test_an_answer_the_passages_carry_clears_the_threshold(
    require_openai_key: None,
) -> None:
    """An answer taken from the passage has to score above the bar, or no answer ever ships."""
    score = await score_faithfulness(
        question=QUESTION, answer=GROUNDED_ANSWER, passages=PASSAGES
    )

    assert score is not None
    assert score >= settings.FAITHFULNESS_THRESHOLD


@pytest.mark.integration
async def test_an_answer_the_passages_do_not_carry_fails_the_threshold(
    require_openai_key: None,
) -> None:
    """The whole point of the gate: claims no passage supports must not reach the user."""
    score = await score_faithfulness(
        question=QUESTION, answer=INVENTED_ANSWER, passages=PASSAGES
    )

    assert score is not None
    assert score < settings.FAITHFULNESS_THRESHOLD
