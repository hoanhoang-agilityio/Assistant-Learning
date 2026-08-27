"""Tests for the ``qa_fallback`` node: what the user is told when no answer could be grounded.

This is the only node standing between a run that failed the faithfulness gate three times
and the user, so what it does not do matters as much as what it says: it must not leave the
rejected answer behind for a caller to read as the result, and it must not claim the
knowledge base was silent when it was the grounding that failed.
"""

import pytest
from langchain_core.messages import AIMessage

from src.core.langgraph.nodes.qa_fallback import (
    QA_FALLBACK_NO_CONTEXT,
    QA_FALLBACK_OUTRO,
    QA_FALLBACK_UNSUPPORTED,
    build_qa_fallback_message,
    qa_fallback,
)
from src.schemas import RetrievedChunk, initial_state

USER_ID = "user-qa-fallback"
QUESTION = "How much protein should I eat?"
UNFAITHFUL_ANSWER = "Take 4 g/kg of protein; a 1974 NASA study proved it."

PASSAGES: list[RetrievedChunk] = [
    {
        "text": "Protein intake of 1.6 g/kg/day maximises training adaptation.",
        "source": "nutrition.docx",
        "score": 0.82,
    }
]


def state_after_scoring(
    passages: list[RetrievedChunk] | None = None, **overrides: object
) -> dict:
    """State as it stands when the faithfulness gate gives up on the QA branch."""
    return (
        initial_state(QUESTION, USER_ID)
        | {
            "qa_answer": UNFAITHFUL_ANSWER,
            "retrieved_context": PASSAGES if passages is None else passages,
            "faithfulness_score": 0.25,
            "qa_retry_count": 3,
        }
        | overrides
    )


# --- The message ------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("passages", "expected_intro"),
    [
        (PASSAGES, QA_FALLBACK_UNSUPPORTED),
        ([], QA_FALLBACK_NO_CONTEXT),
        (None, QA_FALLBACK_NO_CONTEXT),
    ],
)
def test_the_message_says_which_of_the_two_failures_happened(
    passages: list[RetrievedChunk] | None, expected_intro: str
) -> None:
    """Finding nothing and finding something the answer strayed from are different
    problems, and only the second is worth the user rewording the question for."""
    message = build_qa_fallback_message(passages)

    assert message == f"{expected_intro}\n\n{QA_FALLBACK_OUTRO}"


def test_the_message_always_closes_with_a_way_forward() -> None:
    """A run that ends with only a refusal strands the user with nothing to do next."""
    for passages in (PASSAGES, []):
        assert build_qa_fallback_message(passages).endswith(QA_FALLBACK_OUTRO)


# --- The node ---------------------------------------------------------------------------


async def test_the_fallback_message_ends_the_run() -> None:
    """The node's whole job: the user hears why, in the transcript and as the final word."""
    update = await qa_fallback(state_after_scoring())

    expected = build_qa_fallback_message(PASSAGES)
    assert update["final_message"] == expected
    assert update["messages"] == [AIMessage(content=expected)]


async def test_the_rejected_answer_is_not_left_behind() -> None:
    """Ending with `final_message` refusing and `qa_answer` still holding the answer the
    gate rejected is exactly how untrusted output reaches a caller that reads state."""
    update = await qa_fallback(state_after_scoring())

    assert update["qa_answer"] is None


async def test_an_empty_retrieval_is_reported_as_nothing_found() -> None:
    """The QA agent is told to say so rather than answer; the run has to end saying so too."""
    update = await qa_fallback(state_after_scoring(passages=[]))

    assert update["final_message"].startswith(QA_FALLBACK_NO_CONTEXT)
