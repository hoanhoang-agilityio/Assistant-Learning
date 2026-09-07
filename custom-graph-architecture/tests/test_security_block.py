"""Tests for the security block shared by every agent and node system prompt."""

from src.prompts.coach_agent import COACH_AGENT_SYSTEM
from src.prompts.qa_agent import QA_AGENT_SYSTEM
from src.prompts.security import security_block

SYSTEM_PROMPTS = (COACH_AGENT_SYSTEM, QA_AGENT_SYSTEM)


def test_the_tag_is_named_in_the_warning() -> None:
    """A block that names no tag leaves the agent guessing what it protects."""
    assert "`<qa_context>`" in security_block("<qa_context>")


def test_every_prompt_carries_the_same_wording() -> None:
    """Three copies drifting apart is three security policies to keep in sync by hand."""
    assert security_block("<coaching_context>") in COACH_AGENT_SYSTEM
    assert security_block("<qa_context>") in QA_AGENT_SYSTEM


def test_no_instruction_is_split_across_lines() -> None:
    """A rule broken by a mid-sentence newline reaches the model with a stray line break."""
    for prompt in SYSTEM_PROMPTS:
        for line in prompt.splitlines():
            assert not line.startswith(" ")
