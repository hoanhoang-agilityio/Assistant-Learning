"""Prompts owned by the QA agent, read once at import."""

from pathlib import Path

_PROMPTS_DIR = Path(__file__).parent

_QA_AGENT_TEMPLATE = (_PROMPTS_DIR / "qa_agent.md").read_text(encoding="utf-8")


def load_qa_agent_prompt(
    plan_context: str, semantic_context: str = "", episodic_context: str = ""
) -> str:
    """Render the general-knowledge answering prompt.

    Args:
        plan_context: Read-only summary of the user's current plan and macros,
            used to personalise the answer. Empty when they have no plan.
        semantic_context: What is known about this user, rendered from their
            profile *after* this turn's facts were merged into it — the agent
            never looks anything up about the user for itself.
        episodic_context: Earlier sessions, loaded once per turn for the same
            reason. Empty when there are none.

    Returns:
        The formatted QA prompt.
    """
    return _QA_AGENT_TEMPLATE.format(
        plan_context=plan_context or "The user has no saved plan.",
        semantic_context=semantic_context or "Nothing recorded about this user yet.",
        episodic_context=episodic_context or "No earlier conversations with this user.",
    )


__all__ = ["load_qa_agent_prompt"]
