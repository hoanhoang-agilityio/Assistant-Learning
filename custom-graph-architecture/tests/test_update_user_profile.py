"""Tests for the ``update_user_profile`` tool: it always writes when it runs.

Whether an overwrite needs the user's approval is decided before the tool runs at all,
by the ``HumanInTheLoopMiddleware`` wired around ``user_agent``.
"""

import pytest
from langchain.tools import ToolRuntime

import src.tools.profile as profile_tools
from src.schemas import UserAgentContext
from src.tools.profile import update_user_profile

USER_ID = "user-1"


def _runtime() -> ToolRuntime:
    """The runtime the agent builds around a tool call, carrying the user's id."""
    return ToolRuntime(
        state=None,
        config={},
        stream_writer=None,
        tool_call_id="call_1",
        store=None,
        context=UserAgentContext(user_id=USER_ID),
    )


async def _invoke(field: str, value: object) -> object:
    """Call the tool the way the agent's tool node does, so the artifact comes back too."""
    return await update_user_profile.ainvoke(
        {
            "type": "tool_call",
            "name": update_user_profile.name,
            "args": {"field": field, "value": value, "runtime": _runtime()},
            "id": "call_1",
        }
    )


@pytest.fixture
def saved(monkeypatch: pytest.MonkeyPatch) -> list[dict]:
    """Record what the tool saves, in place of the real store."""
    writes: list[dict] = []

    async def save_profile(_user_id: str, updates: dict) -> dict:
        writes.append(updates)
        return updates

    monkeypatch.setattr(profile_tools, "save_profile", save_profile)
    return writes


# --- The field is written whenever the tool runs ----------------------------------------


async def test_the_field_is_written(saved: list[dict]) -> None:
    """By the time this tool runs, an overwrite has already been authorized upstream."""
    result = await _invoke("age", 34)

    assert result.artifact == {
        "status": "written",
        "field": "age",
        "profile": {"age": 34},
    }
    assert saved == [{"age": 34}]


async def test_the_written_reply_names_the_field_and_value(saved: list[dict]) -> None:
    """The user needs to see what was actually saved."""
    result = await _invoke("age", 34)

    assert result.content == "Saved age = 34."


# --- An unknown field never reaches the store -----------------------------------------------


async def test_an_unknown_field_is_rejected_without_touching_the_store(
    saved: list[dict],
) -> None:
    """A field name the model invented must not reach the profile store at all."""
    result = await _invoke("favorite_color", "blue")

    assert result.artifact == {"status": "invalid_field"}
    assert saved == []
