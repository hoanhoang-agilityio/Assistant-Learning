"""Judge evaluators run over whole turns (``scope="traces"``).

Every evaluator here is a plain keyword-only function returning an
``Evaluation`` — that is the entire contract the batch runner needs.

The gates matter as much as the prompts. An evaluator that does not apply to a
turn returns ``[]``, never ``value=0``: zero is a verdict and drags the average
down, empty is an abstention and is simply absent. A metric averaged over turns
it was never meant to judge is a number nobody can act on.

The parameter names ``input`` and ``output`` shadow builtins. They are fixed by
the SDK's evaluator Protocol and cannot be renamed.
"""

from typing import Any

from langfuse import Evaluation

from evals.evaluators.judge import llm_judge, load_prompt

# Intents whose turn produced or modified a plan. `check` reviews a plan the
# user pasted in and `general_qa` never touches one, so neither is a turn whose
# *generated* plan could contradict a stated injury.
PLAN_INTENTS = frozenset({"build_plan", "change_plan"})

MACRO_TERMS = ("macro", "protein", "carb", "kcal", "calorie", "gram", "fat ")

# Wording that asserts state changed. The confirm gate is an `interrupt()` in
# the graph, so a claim here that no confirmation precedes means the narration
# lied about state the graph never committed.
PERSISTENCE_TERMS = (
    "saved",
    "applied",
    "committed",
    "updated your plan",
    "reverted",
    "locked in",
    "all set",
)


async def _judged(
    name: str, input_text: str, output_text: str, metadata: dict | None = None
) -> Evaluation:
    """Run one prompt metric and wrap the verdict as an ``Evaluation``.

    Args:
        name: Metric name — the prompt filename stem and the Langfuse score
            name, which must stay identical and stable to remain chartable.
        input_text: The formatted conversation up to the last message.
        output_text: The formatted last message.
        metadata: Extra fields to attach to the score.

    Returns:
        The score, with the judge's one-sentence reasoning as its comment.
    """
    score = await llm_judge(load_prompt(name), input_text, output_text)
    return Evaluation(
        name=name,
        value=score.score,
        comment=score.reasoning,
        metadata=metadata,
    )


# ----------------------------------------------------------------------
# Generic metrics — apply to any turn that produced text
# ----------------------------------------------------------------------


async def helpfulness(*, input, output, expected_output=None, metadata=None, **kwargs: Any):
    """Score how well the turn served the user. Higher is better."""
    if not input or not output:
        return []
    return await _judged("helpfulness", input, output)


async def relevancy(*, input, output, expected_output=None, metadata=None, **kwargs: Any):
    """Score how on-topic the turn was. Higher is better."""
    if not input or not output:
        return []
    return await _judged("relevancy", input, output)


async def conciseness(*, input, output, expected_output=None, metadata=None, **kwargs: Any):
    """Score how free of padding the turn was. Higher is better."""
    if not input or not output:
        return []
    return await _judged("conciseness", input, output)


async def hallucination(*, input, output, expected_output=None, metadata=None, **kwargs: Any):
    """Score how much the turn invented. **1.0 is bad** — inverted polarity."""
    if not input or not output:
        return []
    return await _judged("hallucination", input, output)


async def toxicity(*, input, output, expected_output=None, metadata=None, **kwargs: Any):
    """Score how hostile the turn was. **1.0 is bad** — inverted polarity."""
    if not input or not output:
        return []
    return await _judged("toxicity", input, output)


# ----------------------------------------------------------------------
# Project metrics — each gated to the turns it can actually judge
# ----------------------------------------------------------------------


async def plan_safety(*, input, output, expected_output=None, metadata=None, **kwargs: Any):
    """Score whether a generated plan respects constraints the user stated.

    Gated to turns that produced or modified a plan. This is the metric a
    helpfulness judge cannot stand in for: a plan that is excellent training
    advice while ignoring a stated injury scores high there and low here.
    """
    if not input or not output:
        return []
    if (metadata or {}).get("intent") not in PLAN_INTENTS:
        return []
    return await _judged("plan_safety", input, output, {"intent": metadata.get("intent")})


async def macro_consistency(*, input, output, expected_output=None, metadata=None, **kwargs: Any):
    """Score whether the macro numbers shown agree with each other and history.

    Gated to turns whose output actually mentions macros — the eval-side mirror
    of ``verify_macro``, catching narration that drifts from state that was
    itself correct.
    """
    if not input or not output:
        return []
    lowered = output.lower()
    if not any(term in lowered for term in MACRO_TERMS):
        return []
    return await _judged("macro_consistency", input, output)


async def confirm_discipline(*, input, output, expected_output=None, metadata=None, **kwargs: Any):
    """Score whether the turn claimed persistence only after a confirmation.

    Gated to turns whose output claims something was persisted — a turn that
    claims nothing cannot violate the gate, and scoring it would bury the
    violations in a sea of trivial 1.0s.
    """
    if not input or not output:
        return []
    lowered = output.lower()
    if not any(term in lowered for term in PERSISTENCE_TERMS):
        return []
    return await _judged("confirm_discipline", input, output)


async def verdict_grounding(*, input, output, expected_output=None, metadata=None, **kwargs: Any):
    """Score whether reported issues exist in the plan under discussion.

    Gated to turns that reached a verdict. An invented ``rubric_ref`` reads as
    authoritative and sends the user to fix something that was never wrong,
    which is why this is worth separating from generic hallucination.
    """
    if not input or not output:
        return []
    verdict = (metadata or {}).get("verdict")
    if verdict is None:
        return []
    return await _judged("verdict_grounding", input, output, {"verdict": verdict})


DOMAIN_EVALUATORS = [
    helpfulness,
    relevancy,
    conciseness,
    hallucination,
    toxicity,
    plan_safety,
    macro_consistency,
    confirm_discipline,
    verdict_grounding,
]

__all__ = [
    "DOMAIN_EVALUATORS",
    "conciseness",
    "confirm_discipline",
    "hallucination",
    "helpfulness",
    "macro_consistency",
    "plan_safety",
    "relevancy",
    "toxicity",
    "verdict_grounding",
]
