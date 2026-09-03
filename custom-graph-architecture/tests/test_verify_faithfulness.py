"""Tests for the ``verify_faithfulness`` node: the score, the counter, the route.

The metric itself is RAGAS'; what matters here is what the node does with the score it
returns. A QA answer only reaches the user once the passages it was written from carry it,
so every way the score can fail to arrive — no answer, no passages, a judge that raised,
a judge that found no statement to judge — has to fail the gate rather than pass silently.
"""

import pytest
from langchain_core.messages import HumanMessage

import src.nodes.faithfulness as faithfulness_node
from src.configs.config import settings
from src.nodes.faithfulness import (
    is_faithful,
    route_after_faithfulness,
    verify_faithfulness,
)
from src.schemas import RetrievedChunk, initial_state
from src.verification import faithfulness

USER_ID = "user-ragas"
QUESTION = "How much protein should I eat?"
ANSWER = "Aim for 1.6 g of protein per kg of bodyweight per day."

PASSAGES: list[RetrievedChunk] = [
    {
        "text": "Protein intake of 1.6 g/kg/day maximises training adaptation.",
        "source": "nutrition.docx",
        "score": 0.82,
    }
]

BELOW_THRESHOLD = settings.FAITHFULNESS_THRESHOLD - 0.2


def state_after_qa(
    answer: str | None = ANSWER,
    passages: list[RetrievedChunk] | None = None,
    **overrides: object,
) -> dict:
    """State as it stands when ``qa_agent`` hands its answer to the gate."""
    return (
        initial_state(QUESTION, USER_ID)
        | {
            "messages": [HumanMessage(content=QUESTION)],
            "qa_answer": answer,
            "retrieved_context": PASSAGES if passages is None else passages,
        }
        | overrides
    )


@pytest.fixture
def scored(monkeypatch: pytest.MonkeyPatch):
    """Return the score the gate should see, without calling the judge model."""

    def use(score: float | None):
        async def score_faithfulness(**kwargs: object) -> float | None:
            return score

        monkeypatch.setattr(faithfulness_node, "score_faithfulness", score_faithfulness)

    return use


# --- The score --------------------------------------------------------------------------


async def test_a_faithful_answer_clears_the_gate(scored) -> None:
    """The only way a QA answer reaches the user."""
    scored(0.95)

    update = await verify_faithfulness(state_after_qa())

    assert update["faithfulness_score"] == 0.95
    assert update["qa_retry_count"] == 0
    assert update["qa_outcome"] == "answered"
    assert [message.content for message in update["messages"]] == [ANSWER]


async def test_the_threshold_itself_passes(scored) -> None:
    """The spec is `>= 0.9`; scoring exactly the threshold is a pass, not a retry."""
    scored(settings.FAITHFULNESS_THRESHOLD)

    update = await verify_faithfulness(state_after_qa())

    assert update["qa_retry_count"] == 0


async def test_an_unfaithful_answer_is_kept_with_its_score(scored) -> None:
    """The retry prompt shows the agent the rejected answer and what it scored."""
    scored(BELOW_THRESHOLD)

    update = await verify_faithfulness(state_after_qa())

    assert update == {
        "faithfulness_score": BELOW_THRESHOLD,
        "qa_retry_count": 1,
        "messages": [],
    }
    assert "qa_outcome" not in update


async def test_the_gate_scores_the_question_answer_and_passages(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Faithfulness is the answer against its own retrieval; any other pairing is meaningless."""
    seen: dict = {}

    async def score_faithfulness(**kwargs: object) -> float:
        seen.update(kwargs)
        return 1.0

    monkeypatch.setattr(faithfulness_node, "score_faithfulness", score_faithfulness)

    await verify_faithfulness(state_after_qa())

    assert seen == {"question": QUESTION, "answer": ANSWER, "passages": PASSAGES}


# --- Answers that cannot be scored --------------------------------------------------------


async def test_no_answer_at_all_fails_the_gate() -> None:
    """``qa_agent`` returns no answer when it fails; nothing may pass on an empty answer."""
    update = await verify_faithfulness(state_after_qa(answer=None))

    assert update == {"faithfulness_score": None, "qa_retry_count": 1, "messages": []}


async def test_an_answer_with_no_retrieved_passages_fails_the_gate() -> None:
    """With nothing retrieved there is nothing the answer could be faithful to."""
    update = await verify_faithfulness(state_after_qa(passages=[]))

    assert update == {"faithfulness_score": None, "qa_retry_count": 1, "messages": []}


async def test_a_missing_score_fails_the_gate(scored) -> None:
    """A judge that raised or found no statement to judge has not cleared the answer."""
    scored(None)

    update = await verify_faithfulness(state_after_qa())

    assert update == {"faithfulness_score": None, "qa_retry_count": 1, "messages": []}


# --- The retry counter --------------------------------------------------------------------


async def test_each_unfaithful_attempt_is_counted(scored) -> None:
    """The counter is what bounds the loop; a failure that does not count never ends it."""
    scored(BELOW_THRESHOLD)

    update = await verify_faithfulness(state_after_qa(qa_retry_count=1))

    assert update["qa_retry_count"] == 2


async def test_a_pass_clears_the_count(scored) -> None:
    """A later turn on the same thread starts fresh rather than one failure from fallback."""
    scored(0.95)

    update = await verify_faithfulness(state_after_qa(qa_retry_count=2))

    assert update["qa_retry_count"] == 0


# --- Routing ------------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("score", "expected"),
    [
        (None, False),
        (0.0, False),
        (BELOW_THRESHOLD, False),
        (settings.FAITHFULNESS_THRESHOLD, True),
        (1.0, True),
    ],
)
def test_the_threshold_decides_what_counts_as_faithful(
    score: float | None, expected: bool
) -> None:
    """One predicate behind both the node's verdict and the route; they cannot disagree."""
    assert is_faithful(score) is expected


def test_a_faithful_answer_routes_past_the_gate() -> None:
    """The only way out of the QA branch with an answer."""
    state = state_after_qa(
        faithfulness_score=1.0, qa_retry_count=settings.QA_MAX_RETRIES
    )

    assert route_after_faithfulness(state) == "pass"


@pytest.mark.parametrize(
    ("retry_count", "expected"),
    [
        (0, "retry"),
        (settings.QA_MAX_RETRIES - 1, "retry"),
        (settings.QA_MAX_RETRIES, "fallback"),
        (settings.QA_MAX_RETRIES + 1, "fallback"),
    ],
)
def test_an_unfaithful_answer_routes_on_the_budget(
    retry_count: int, expected: str
) -> None:
    """Back to the agent while there are attempts left, and to the fallback after."""
    state = state_after_qa(
        faithfulness_score=BELOW_THRESHOLD, qa_retry_count=retry_count
    )

    assert route_after_faithfulness(state) == expected


async def test_the_agent_is_sent_back_a_bounded_number_of_times(scored) -> None:
    """The loop the spec bounds: the answer never improves, so the run has to give up."""
    scored(BELOW_THRESHOLD)
    state = state_after_qa()
    routes = []

    for _ in range(settings.QA_MAX_RETRIES):
        state |= await verify_faithfulness(state)
        routes.append(route_after_faithfulness(state))

    assert routes == ["retry"] * (settings.QA_MAX_RETRIES - 1) + ["fallback"]


# --- Scoring ------------------------------------------------------------------------------


class _StubMetric:
    """A stand-in for the RAGAS metric, recording what it was asked to score."""

    def __init__(self, value: float) -> None:
        self.value = value
        self.seen: dict = {}

    async def ascore(self, **kwargs: object):
        self.seen.update(kwargs)
        return type("MetricResult", (), {"value": self.value})()


def _use_metric(monkeypatch: pytest.MonkeyPatch, metric: object) -> None:
    """Serve a stub metric so scoring runs without a judge model."""
    monkeypatch.setattr(faithfulness, "build_faithfulness_metric", lambda: metric)


async def test_scoring_hands_ragas_the_passage_text(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """RAGAS takes plain strings; handing it the chunk dicts would score the metadata too."""
    metric = _StubMetric(0.75)
    _use_metric(monkeypatch, metric)

    score = await faithfulness.score_faithfulness(
        question=QUESTION, answer=ANSWER, passages=PASSAGES
    )

    assert score == 0.75
    assert metric.seen["retrieved_contexts"] == [PASSAGES[0]["text"]]


async def test_scoring_reports_nothing_when_ragas_finds_no_statement(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """RAGAS returns NaN for an answer it could not decompose, and NaN >= 0.9 is False."""
    _use_metric(monkeypatch, _StubMetric(float("nan")))

    score = await faithfulness.score_faithfulness(
        question=QUESTION, answer=ANSWER, passages=PASSAGES
    )

    assert score is None


async def test_scoring_survives_a_judge_that_raises(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A judge outage must fail the answer, not the run: the node still gets to route."""

    class _Failing:
        async def ascore(self, **kwargs: object):
            raise RuntimeError("judge unavailable")

    _use_metric(monkeypatch, _Failing())

    score = await faithfulness.score_faithfulness(
        question=QUESTION, answer=ANSWER, passages=PASSAGES
    )

    assert score is None


@pytest.mark.parametrize(
    ("question", "answer", "passages"),
    [
        ("", ANSWER, PASSAGES),
        (QUESTION, None, PASSAGES),
        (QUESTION, "", PASSAGES),
        (QUESTION, ANSWER, []),
    ],
)
async def test_scoring_never_calls_the_judge_without_all_three_inputs(
    monkeypatch: pytest.MonkeyPatch,
    question: str,
    answer: str | None,
    passages: list[RetrievedChunk],
) -> None:
    """RAGAS raises on a missing input; the gate answers for it rather than paying for it."""

    class _Unreachable:
        async def ascore(self, **kwargs: object):
            raise AssertionError(
                "the judge must not be called without all three inputs"
            )

    _use_metric(monkeypatch, _Unreachable())

    assert (
        await faithfulness.score_faithfulness(
            question=question, answer=answer, passages=passages
        )
        is None
    )


def test_ragas_imports_behind_the_compatibility_stub() -> None:
    """RAGAS 0.4.3 imports a langchain-community module 0.4 removed; without the stub it
    cannot be imported at all, and the gate would fail every answer in production while
    every stubbed test above still passed."""
    faithfulness.install_vertexai_stub()

    from ragas.metrics.collections.faithfulness import Faithfulness  # noqa: PLC0415

    assert Faithfulness is not None
