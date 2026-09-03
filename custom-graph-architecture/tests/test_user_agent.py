"""Tests for the ``user_agent`` node and the approval gate wired around its profile tool.

Whether an overwrite pauses for the user is decided by ``_overwrites_a_stored_value``, the
``when`` predicate ``HumanInTheLoopMiddleware`` calls before ``update_user_profile`` ever
runs — not by the tool itself (``test_update_user_profile.py`` covers the tool).
"""

import sys

from langchain_core.messages import AIMessage
from langgraph.prebuilt.tool_node import ToolCallRequest, ToolRuntime

from src.agents.user import (
    _overwrites_a_stored_value,
    _profile_completion_update,
    _user_outcome,
    route_after_user_agent,
    user_agent,
)
from src.enums import UserAgentRoute
from src.schemas import GraphState, UserAgentContext, initial_state

user_module = sys.modules[user_agent.__module__]

USER_ID = "user-1"


def _request(profile: dict | None, field: str) -> ToolCallRequest:
    """A tool-call request for ``update_user_profile``, as the middleware would build it."""
    return ToolCallRequest(
        tool_call={
            "type": "tool_call",
            "name": "update_user_profile",
            "args": {"field": field, "value": "new"},
            "id": "call_1",
        },
        tool=None,
        state=None,
        runtime=ToolRuntime(
            state=None,
            context=UserAgentContext(user_id=USER_ID, profile=profile),
            config={},
            stream_writer=None,
            tool_call_id="call_1",
            store=None,
        ),
    )


# --- The interrupt predicate -----------------------------------------------------------


def test_a_field_already_on_file_needs_approval() -> None:
    """An overwrite of a real value is exactly what the approval gate exists for."""
    assert _overwrites_a_stored_value(_request({"age": 30}, "age")) is True


def test_a_blank_field_does_not_need_approval() -> None:
    """Nothing to overwrite means nothing to confirm."""
    assert _overwrites_a_stored_value(_request({"age": "   "}, "age")) is False


def test_a_field_missing_from_the_profile_does_not_need_approval() -> None:
    """A field never recorded at all is a first write, not an overwrite."""
    assert _overwrites_a_stored_value(_request({"age": 30}, "sex")) is False


def test_no_profile_at_all_never_needs_approval() -> None:
    """A brand new user has nothing on file to overwrite."""
    assert _overwrites_a_stored_value(_request(None, "age")) is False


# --- The node loads a fresh profile for the gate to read --------------------------------


class _StubUserAgent:
    """Records the context it was invoked with, and returns a fixed result."""

    def __init__(self, result: dict) -> None:
        self.result = result
        self.contexts: list[UserAgentContext] = []

    async def ainvoke(self, _inputs: dict, context: UserAgentContext) -> dict:
        self.contexts.append(context)
        return self.result


async def test_the_node_loads_the_profile_fresh_for_the_gate(
    monkeypatch,
) -> None:
    """A stale ``state['profile']`` must not let a real overwrite slip past the gate unseen."""

    async def load_profile(_user_id: str) -> dict:
        return {"age": 30}

    monkeypatch.setattr(user_module, "load_profile", load_profile)

    stub = _StubUserAgent({"messages": [AIMessage(content="done")]})
    monkeypatch.setattr(user_module, "build_user_agent", lambda: stub)

    state = initial_state("what's my age?", USER_ID) | {"profile": None}
    await user_agent(state)

    assert stub.contexts == [UserAgentContext(user_id=USER_ID, profile={"age": 30})]


async def test_a_failed_run_still_reports_the_freshly_loaded_profile(
    monkeypatch,
) -> None:
    """The fallback on error should not regress to a stale or empty profile either."""

    async def load_profile(_user_id: str) -> dict:
        return {"age": 30}

    monkeypatch.setattr(user_module, "load_profile", load_profile)

    class _FailingUserAgent:
        async def ainvoke(self, *_args: object, **_kwargs: object) -> dict:
            raise RuntimeError("boom")

    monkeypatch.setattr(user_module, "build_user_agent", _FailingUserAgent)

    result = await user_agent(initial_state("hi", USER_ID))

    assert result == {"profile": {"age": 30}, "messages": []}


# --- Completeness is only checked when a waiting plan asked for it ----------------------

COMPLETE_PROFILE = {
    "age": 27,
    "sex": "MALE",
    "height_cm": 178.0,
    "current_weight_kg": 80.0,
    "activity_level": "MODERATE",
    "goal": "FAT_LOSS",
    "training_days_per_week": 4,
}


def test_an_ad_hoc_turn_never_touches_profile_status() -> None:
    """A question with no plan waiting on it must not bounce through the onboarding form."""
    assert _profile_completion_update(None, False) == {}
    assert _profile_completion_update(COMPLETE_PROFILE, False) == {}


def test_a_plan_still_missing_fields_reports_need_input() -> None:
    assert _profile_completion_update({"age": 27}, True) == {
        "profile_status": "need_input"
    }


def test_a_plan_with_a_complete_profile_reports_ready() -> None:
    """Already complete right after the ad-hoc turn means the form has nothing left to ask."""
    assert _profile_completion_update(COMPLETE_PROFILE, True) == {
        "profile_status": "ready",
    }


def test_no_profile_at_all_with_a_waiting_plan_reports_need_input() -> None:
    """A brand new user is exactly the ``need_input`` case, not an edge case of it."""
    assert _profile_completion_update(None, True) == {"profile_status": "need_input"}


# --- What the supervisor is told the turn came to -------------------------------------------


def test_a_handled_turn_reports_the_profile_part_answered() -> None:
    """Without it the supervisor, which never sees the reply, would send the turn back here."""
    assert _user_outcome(None) == "answered"
    assert _user_outcome("ready") == "answered"


def test_a_turn_still_owed_fields_reports_needs_input() -> None:
    """The form has yet to run, so the profile part is not something the supervisor can call done."""
    assert _user_outcome("need_input") == "needs_input"


# --- Routing on profile_status ------------------------------------------------------------


def _routed(status: str | None) -> GraphState:
    return initial_state("hi", USER_ID) | {"profile_status": status}


def test_a_plan_still_missing_fields_goes_to_the_form() -> None:
    """The only case the form exists for."""
    state = _routed("need_input")
    assert route_after_user_agent(state) == UserAgentRoute.NEEDS_MORE_INFO


def test_a_plan_now_complete_skips_the_form() -> None:
    """Already satisfied by the ad-hoc turn — no reason to ask again."""
    state = _routed("ready")
    assert route_after_user_agent(state) == UserAgentRoute.DONE


def test_an_unrelated_ad_hoc_turn_always_finishes() -> None:
    """Nothing waiting on the profile means the form must never appear."""
    state = _routed(None)
    assert route_after_user_agent(state) == UserAgentRoute.DONE
