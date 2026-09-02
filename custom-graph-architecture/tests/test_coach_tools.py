"""Tests for the coach agent's tool set: what the model is offered, and on what terms."""

import json

import pytest
from langchain_core.tools import BaseTool

from src.tools import (
    COACH_TOOLS,
    calc_macro,
    get_plan,
    load_exercise,
    load_template,
    recall_memory,
)

# Renaming a tool changes the agent's interface rather than its implementation: the names
# reach the model, and traces are read by them. A rename should fail here and be a
# decision, not a silent edit.
COACH_TOOL_NAMES = {"get_plan", "load_template", "load_exercise", "recall_memory"}

# What the user told the collection loop. A tool that took any of these as an argument
# would let the model supply them, and a supplied profile field is an invented one.
PROFILE_ARGUMENTS = {
    "profile",
    "age",
    "sex",
    "height_cm",
    "current_weight_kg",
    "weight_kg",
    "activity_level",
    "injuries",
    "equipment",
    "available_equipment",
}

TOOL_IDS = [tool.name for tool in COACH_TOOLS]


# --- The set ------------------------------------------------------------------------------


def test_the_coach_has_only_the_lookups_it_cannot_be_handed_up_front() -> None:
    """Templates, exercises and stored memory follow the coach's choices; macros do not."""
    assert {tool.name for tool in COACH_TOOLS} == COACH_TOOL_NAMES


def test_the_macro_arithmetic_is_not_a_round_trip_the_coach_pays_for() -> None:
    """A pure function of the profile, computed into the context instead of asked for."""
    assert calc_macro not in COACH_TOOLS


def test_the_tools_are_registered_once_each() -> None:
    """Two entries of one name bind twice and leave the model's choice ambiguous."""
    assert len(COACH_TOOLS) == len(COACH_TOOL_NAMES)


@pytest.mark.parametrize("tool", COACH_TOOLS, ids=TOOL_IDS)
def test_every_entry_is_something_the_model_can_be_given(tool: BaseTool) -> None:
    """A bare function in the list fails at bind time, which is a run that never starts."""
    assert isinstance(tool, BaseTool)


# --- What the model is told ---------------------------------------------------------------


@pytest.mark.parametrize("tool", COACH_TOOLS, ids=TOOL_IDS)
def test_every_tool_says_what_it_is_for(tool: BaseTool) -> None:
    """The description is the whole basis on which the model picks between them."""
    assert tool.description.strip()


@pytest.mark.parametrize("tool", COACH_TOOLS, ids=TOOL_IDS)
def test_every_tools_arguments_reach_the_model_as_json_schema(tool: BaseTool) -> None:
    """An argument schema that will not serialise is a tool the request cannot carry."""
    assert json.dumps(tool.tool_call_schema.model_json_schema())


@pytest.mark.parametrize("tool", COACH_TOOLS, ids=TOOL_IDS)
def test_the_runtime_is_injected_rather_than_asked_for(tool: BaseTool) -> None:
    """Offered as an argument, the model would have to invent a `ToolRuntime` to call at all."""
    assert "runtime" not in tool.args


@pytest.mark.parametrize("tool", COACH_TOOLS, ids=TOOL_IDS)
def test_no_tool_lets_the_model_supply_the_users_own_data(tool: BaseTool) -> None:
    """Body metrics and injuries are the inputs a hallucinated answer would differ by."""
    assert not PROFILE_ARGUMENTS & set(tool.args)


# --- Where each tool gets the user from ---------------------------------------------------


def test_the_tools_that_depend_on_the_user_read_the_runtime() -> None:
    """Exercise filtering and macro arithmetic are both wrong without the real profile."""
    assert "runtime" in load_exercise.args_schema.model_fields
    assert "runtime" in calc_macro.args_schema.model_fields


def test_the_memory_lookup_is_scoped_to_the_runtimes_user() -> None:
    """Offered `user_id`, the model could read whichever user's memory it named."""
    assert "runtime" in recall_memory.args_schema.model_fields
    assert "user_id" not in recall_memory.args


def test_the_template_lookup_asks_for_nothing_it_does_not_use() -> None:
    """A template is chosen by goal and by week alone; the profile would not narrow it."""
    assert set(load_template.args) == {"goal", "days_per_week"}


def test_the_stored_plan_is_read_for_the_runtimes_user_alone() -> None:
    """Offered `user_id`, the model could read whichever user's plan it named."""
    assert "runtime" in get_plan.args_schema.model_fields
    assert not set(get_plan.args)
