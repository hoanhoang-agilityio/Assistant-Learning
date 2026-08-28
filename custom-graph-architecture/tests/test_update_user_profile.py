"""Tests for the ``update_user_profile`` tool: direct write vs. staged overwrite."""

import pytest
from langchain.tools import ToolRuntime

import src.tools.profile as profile_tools
from src.schemas import UserAgentContext
from src.services.profile import UserContext
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
def stored_profile(monkeypatch: pytest.MonkeyPatch):
    """Serve one stored profile, and record what the tool saves back."""
    saved: list[dict] = []

    def use(profile: dict | None) -> list[dict]:
        async def load_user_context(_user_id: str) -> UserContext:
            return UserContext(profile=profile)

        async def save_profile(_user_id: str, updates: dict) -> dict:
            saved.append(updates)
            return {**(profile or {}), **updates}

        monkeypatch.setattr(profile_tools, "load_user_context", load_user_context)
        monkeypatch.setattr(profile_tools, "save_profile", save_profile)
        return saved

    return use


# --- A blank field is written immediately -------------------------------------------------


async def test_a_field_with_nothing_on_file_is_written_immediately(
    stored_profile,
) -> None:
    """Nothing on file yet, so there is nothing to confirm before writing it."""
    saved = stored_profile({"age": None})

    result = await _invoke("age", 34)

    assert result.artifact == {
        "status": "written",
        "field": "age",
        "profile": {"age": 34},
    }
    assert saved == [{"age": 34}]


async def test_a_blank_string_on_file_is_also_written_immediately(
    stored_profile,
) -> None:
    """An empty string on file is not a value worth confirming an overwrite against."""
    saved = stored_profile({"sex": "   "})

    result = await _invoke("sex", "male")

    assert result.artifact["status"] == "written"
    assert saved == [{"sex": "male"}]


async def test_no_profile_on_record_at_all_is_the_same_as_a_blank_field(
    stored_profile,
) -> None:
    """A first-time user has nothing to overwrite either."""
    stored_profile(None)

    result = await _invoke("age", 34)

    assert result.artifact["status"] == "written"


async def test_the_written_reply_names_the_field_and_value(stored_profile) -> None:
    """The user needs to see what was actually saved, not just that something was."""
    stored_profile({"age": None})

    result = await _invoke("age", 34)

    assert result.content == "Saved age = 34."


# --- An existing value is staged instead of overwritten ------------------------------------


async def test_an_existing_value_is_staged_instead_of_overwritten(
    stored_profile,
) -> None:
    """A value already on file needs the user's confirmation before it changes."""
    saved = stored_profile({"age": 30})

    result = await _invoke("age", 34)

    assert result.artifact == {
        "status": "pending_approval",
        "field": "age",
        "previous": 30,
        "value": 34,
    }
    assert saved == []


async def test_staging_an_overwrite_never_touches_the_store(stored_profile) -> None:
    """Nothing is written until the caller approves it through the hitl gate."""
    saved = stored_profile({"age": 30})

    await _invoke("age", 34)

    assert saved == []


async def test_the_staged_reply_asks_for_confirmation(stored_profile) -> None:
    """The user needs to know this change did not just happen."""
    stored_profile({"age": 30})

    result = await _invoke("age", 34)

    assert "confirmation" in result.content


# --- An unknown field never reaches the store -----------------------------------------------


async def test_an_unknown_field_is_rejected_without_touching_the_store(
    stored_profile,
) -> None:
    """A field name the model invented must not reach the profile store at all."""
    saved = stored_profile({"age": 30})

    result = await _invoke("favorite_color", "blue")

    assert result.artifact == {"status": "invalid_field"}
    assert saved == []
