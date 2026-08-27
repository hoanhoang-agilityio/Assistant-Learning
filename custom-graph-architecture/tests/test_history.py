"""Tests for `trim_history`: what a long-running conversation looks like to an agent."""

import pytest
from langchain_core.messages import AIMessage, HumanMessage

from src.core.configs.config import settings
from src.core.langgraph.agents.history import trim_history


def test_a_short_conversation_is_kept_whole() -> None:
    """Nothing over budget, nothing to cut."""
    messages = [HumanMessage(content="hi"), AIMessage(content="hello")]

    assert trim_history(messages) == messages


def test_a_long_conversation_is_cut_to_the_most_recent_turns(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Old turns cost the same tokens on every later call; the budget bounds that."""
    monkeypatch.setattr(settings, "HISTORY_MAX_TOKENS", 5)
    messages = [
        HumanMessage(content="turn one " * 20),
        AIMessage(content="reply one " * 20),
        HumanMessage(content="turn two"),
        AIMessage(content="reply two"),
    ]

    trimmed = trim_history(messages)

    assert messages[0] not in trimmed
    assert trimmed[-1] == messages[-1]


def test_the_cut_lands_on_a_human_turn(monkeypatch: pytest.MonkeyPatch) -> None:
    """An agent shown a stray AI reply with no request behind it has nothing to answer."""
    monkeypatch.setattr(settings, "HISTORY_MAX_TOKENS", 5)
    messages = [
        HumanMessage(content="turn one"),
        AIMessage(content="reply one " * 20),
        HumanMessage(content="turn two"),
    ]

    trimmed = trim_history(messages)

    assert isinstance(trimmed[0], HumanMessage)


def test_an_empty_history_stays_empty() -> None:
    """The very first turn of a conversation has nothing to trim."""
    assert trim_history([]) == []
