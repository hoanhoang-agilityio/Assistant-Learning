"""LLM judge for the Supervisor's user_intent classification.

Phase 2 of the intent-aware orchestration refactor (see
docs/reports/execution_plan_refactor/). Built and unit-tested here; not yet called from
supervisor_node -- that wiring is Phase 3. Mirrors judge_request_type
(core/agents/request_type_judge.py) and judge_topic_scope
(core/agents/topic_scope_judge.py) exactly: same override/test-fixture shape, same LLM-call
plumbing.

`analyze` is deliberately absent from `UserIntent`'s literal type (design doc §7) -- not
just unimplemented downstream, but unconstructible here, so a run can never dead-end on a
workflow that doesn't exist yet.

`mentions_submitted_plan` and `touches_goal_or_constraints` are both booleans, never plan
text (design review F2): an LLM asked to reproduce a pasted plan inside a structured-output
field can subtly paraphrase, truncate, or alter it, which would undermine the entire point
of a verification feature. The submitted plan's actual text is sourced exclusively from
`CreateRunRequest.submitted_plan_text` (Phase 4), never from this judge. Likewise,
`touches_goal_or_constraints` replaces a hand-rolled keyword heuristic (design review F11)
with a judge-provided signal, consistent with every other nuanced request-shape decision in
this codebase being judge-based rather than keyword-based.
"""

from collections.abc import Callable
from typing import Literal

from langchain_core.messages import HumanMessage, SystemMessage
from pydantic import BaseModel, Field

from core.llm.factory import invoke_standard_structured_output
from core.llm.metrics import reset_llm_metrics_node, set_llm_metrics_node
from core.llm.prompt_fragments import JSON_ONLY_INSTRUCTION

# Canonical home of UserIntent (design doc §7): core.agents.run_execution_plan imports it
# from here for RunExecutionPlan.user_intent's field type, rather than this module
# importing from there -- the reverse direction would be a circular import, since
# run_execution_plan.resolve_workflow (Phase 2) needs UserIntentJudgement from this module.
UserIntent = Literal["generate", "edit", "verify"]


class UserIntentJudgement(BaseModel):
    """LLM verdict on what action the user wants performed against their fitness plan."""

    user_intent: UserIntent
    reason: str = Field(description="One short sentence explaining the verdict.")
    mentions_submitted_plan: bool = Field(
        description=(
            "True if the user has pasted or clearly referenced an existing plan they "
            "want checked, as opposed to asking for a new one to be created."
        )
    )
    touches_goal_or_constraints: bool = Field(
        description=(
            "Only meaningful when user_intent is 'edit'. True if the requested change "
            "affects the underlying goal, constraints, or training days per week, rather "
            "than only the workout's content (exercises, sets, reps)."
        )
    )


UserIntentJudge = Callable[[str], UserIntentJudgement]

_JUDGE_OVERRIDE: UserIntentJudge | None = None

_JUDGE_SYSTEM_PROMPT = (
    """You are the intent classifier for a fitness planning assistant.

Classify the user's message into exactly one of these user_intent values:

- generate: the user wants a new plan created (a workout program, training schedule, or
  macro targets), with nothing existing to build from.
- edit: the user already has a plan from this assistant and wants a change made to it
  (add/remove a day, swap an exercise, adjust macros, change the goal or schedule).
- verify: the user has their own existing plan -- written by them, or from somewhere
  else entirely -- and wants it checked or reviewed, not changed or regenerated.

Examples:

"Build me a 4-day upper/lower split."
-> generate

"Can you swap out my bench press for something else?"
-> edit (touches_goal_or_constraints: false -- only exercise content changes)

"Actually, I want to switch from fat loss to strength now, can you adjust my plan?"
-> edit (touches_goal_or_constraints: true -- changes the underlying goal)

"Here's the plan I've been running: [pasted plan]. Is this actually safe and
well-balanced?"
-> verify (mentions_submitted_plan: true)

Only set touches_goal_or_constraints to true when user_intent is edit. Only set
mentions_submitted_plan to true when the user has actually included or clearly referenced
their own existing plan's content, not merely mentioned having one in passing."""
    + JSON_ONLY_INSTRUCTION
    + "\n"
)


def configure_user_intent_judge(judge: UserIntentJudge | None) -> None:
    """Override the user-intent judge (used in tests)."""
    global _JUDGE_OVERRIDE
    _JUDGE_OVERRIDE = judge


def judge_user_intent(query: str) -> UserIntentJudgement:
    """Ask the LLM what action the user wants performed. Raises on LLM/API failure."""
    if _JUDGE_OVERRIDE is not None:
        return _JUDGE_OVERRIDE(query)
    token = set_llm_metrics_node("intent_judge")
    try:
        return invoke_standard_structured_output(
            UserIntentJudgement,
            [
                SystemMessage(content=_JUDGE_SYSTEM_PROMPT),
                HumanMessage(content=query),
            ],
            prompt_cache_key="intent_judge",
        )
    finally:
        reset_llm_metrics_node(token)
