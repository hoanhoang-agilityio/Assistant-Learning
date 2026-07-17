"""LLM-based classification of follow-up plan-edit requests."""

from collections.abc import Callable

from langchain_core.messages import HumanMessage, SystemMessage

from core.llm.factory import invoke_standard_structured_output
from core.llm.metrics import reset_llm_metrics_node, set_llm_metrics_node
from core.llm.payload import compact_json
from core.llm.prompt_fragments import JSON_ONLY_INSTRUCTION
from core.subgraphs.fitness.schema import EditOperation

EditClassifier = Callable[[str, list[str]], EditOperation]

_CLASSIFIER_OVERRIDE: EditClassifier | None = None

_EDIT_CLASSIFIER_SYSTEM_PROMPT = (
    """You classify a user's follow-up request against their existing workout plan into
exactly one of five operations:

- ADD_DAY: the user wants an additional training day added to the plan.
- REMOVE_DAY: the user wants a training day removed from the plan.
- REPLACE_EXERCISE: the user wants one specific existing exercise swapped for a
  different one. Only use this when both the exercise to replace (target_exercise)
  and its replacement (replacement_exercise) are clear from the request. Match
  target_exercise against the provided current_exercise_names when possible.
- UPDATE_MACROS: the user wants a change to calories, protein, carbs, fat, or macro
  targets only, with no change to the training days.
- OTHER: anything else, including changing the split/program structure, requests
  that don't map cleanly to the above, or ambiguous requests.

Only set target_exercise/replacement_exercise for REPLACE_EXERCISE; leave them null
otherwise. Do not guess an operation you are not confident about -- prefer OTHER."""
    + JSON_ONLY_INSTRUCTION
    + "\n"
)


def configure_edit_classifier(classifier: EditClassifier | None) -> None:
    """Override the edit classifier (used in tests)."""
    global _CLASSIFIER_OVERRIDE
    _CLASSIFIER_OVERRIDE = classifier


def classify_edit_operation(
    revision_feedback: str,
    current_exercise_names: list[str],
) -> EditOperation:
    """Classify a follow-up revision request into a structured edit operation."""
    if _CLASSIFIER_OVERRIDE is not None:
        return _CLASSIFIER_OVERRIDE(revision_feedback, current_exercise_names)
    payload = {
        "request": revision_feedback.strip(),
        "current_exercise_names": current_exercise_names,
    }
    token = set_llm_metrics_node("edit_classifier")
    try:
        return invoke_standard_structured_output(
            EditOperation,
            [
                SystemMessage(content=_EDIT_CLASSIFIER_SYSTEM_PROMPT),
                HumanMessage(content=compact_json(payload)),
            ],
            prompt_cache_key="edit_classifier",
        )
    finally:
        reset_llm_metrics_node(token)
