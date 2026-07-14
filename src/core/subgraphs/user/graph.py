from functools import lru_cache
from typing import Any

from langchain_core.runnables import RunnableConfig
from langgraph.graph import END, START, StateGraph
from langgraph.graph.state import CompiledStateGraph
from langgraph.types import interrupt

from core.agents.state import OrchestrationState
from core.profile.schema import CONSTRAINT_FIELDS, PROFILE_FIELDS
from core.subgraphs.user.state import UserProfileResult, UserState
from core.subgraphs.user.utils import (
    extract_profile,
    merge_form_submission,
    persist_profile,
    validate_profile_completeness,
    validate_profile_schema,
)
from core.subgraphs.wrapper import merge_subgraph_updates


def _extract_node(state: UserState) -> dict:
    profile = extract_profile(
        state["query"],
        state["user_profile"],
        state["constraints"],
        revision_feedback=state.get("revision_feedback"),
    )
    return {"profile": profile, "used_llm_extraction": True}


def _validate_node(state: UserState) -> dict:
    completeness = validate_profile_completeness(state["profile"])
    validation_errors = validate_profile_schema(state["profile"])
    return {
        "missing_fields": completeness["missing_fields"],
        "feasibility_issues": completeness["feasibility_issues"],
        "validation_errors": validation_errors,
        "complete": not completeness["missing_fields"],
        "valid": not validation_errors and not completeness["feasibility_requires_review"],
    }


def _form_node(state: UserState) -> dict:
    """Pause for the user to submit/edit the profile form, then merge the response.

    This is the only place in the codebase that uses LangGraph's dynamic ``interrupt()`` --
    every other pause (the top-level ``hitl`` node) uses the static ``interrupt_before``
    mechanism instead. See ``get_user_subgraph``/``invoke_user_subgraph`` for why this
    subgraph needs its own checkpointer wiring to support it.
    """
    submission = interrupt(
        {
            "type": "profile_form",
            "profile": state["profile"],
            "missing_fields": state["missing_fields"],
            "feasibility_issues": state["feasibility_issues"],
            "validation_errors": state["validation_errors"],
        }
    )
    form_data = submission if isinstance(submission, dict) else {}
    merged = merge_form_submission(state["profile"], form_data)
    return {"profile": merged}


def _persist_node(state: UserState) -> dict:
    persist_profile(state["workspace_path"], state["profile"])
    return {}


def _route_after_validate(state: UserState) -> str:
    if state["complete"] and state["valid"]:
        return "persist"
    return "form"


def build_user_subgraph() -> CompiledStateGraph:
    """Compile the User subgraph StateGraph.

    Edges: ``extract -> validate -> {persist | form}``, with ``form -> validate`` looping back
    after every submission so a still-incomplete/invalid resubmission re-enters the form with
    fresh feedback instead of silently proceeding.
    """
    graph = StateGraph(UserState)
    graph.add_node("extract", _extract_node)
    graph.add_node("validate", _validate_node)
    graph.add_node("form", _form_node)
    graph.add_node("persist", _persist_node)
    graph.add_edge(START, "extract")
    graph.add_edge("extract", "validate")
    graph.add_conditional_edges(
        "validate",
        _route_after_validate,
        {"persist": "persist", "form": "form"},
    )
    graph.add_edge("form", "validate")
    graph.add_edge("persist", END)
    # Unlike the other four subgraphs (compiled bare, invoked via an unconfigured .invoke()),
    # this graph pauses via interrupt() in `_form_node` and needs a checkpointer to durably
    # record/resume that pause. `checkpointer=True` delegates to whichever checkpointer the
    # *parent* graph is compiled with, resolved from the config passed at invoke time --
    # see `invoke_user_subgraph`, which must forward that config through.
    return graph.compile(checkpointer=True)


@lru_cache
def get_user_subgraph() -> CompiledStateGraph:
    return build_user_subgraph()


def to_user_state(state: OrchestrationState) -> UserState:
    return UserState(
        query=state["query"],
        workspace_path=state["workspace_path"],
        user_profile=state["user_profile"],
        constraints=state["constraints"],
        revision_feedback=state.get("revision_feedback"),
        profile={},
        missing_fields=[],
        feasibility_issues=[],
        validation_errors=[],
        complete=False,
        valid=False,
        used_llm_extraction=False,
    )


def invoke_user_subgraph(state: OrchestrationState, config: RunnableConfig) -> dict:
    """Run the User subgraph and map results back to orchestration updates.

    `config` must be the caller's own graph-invoke config (forwarded from whatever parent
    node is executing this), so `interrupt()`/resume inside `_form_node` is backed by a real
    checkpointer. When the subgraph pauses, `get_user_subgraph().invoke(...)` raises
    `GraphInterrupt` instead of returning -- that exception is intentionally left to propagate
    to the parent's executor, which records the pause at this node's boundary. Callers must
    not swallow it.
    """
    result = get_user_subgraph().invoke(to_user_state(state), config)
    profile_result: UserProfileResult = {
        "profile": result["profile"],
        "constraints": {
            field: result["profile"][field]
            for field in CONSTRAINT_FIELDS
            if field in result["profile"]
        },
        "complete": result["complete"],
        "valid": result["valid"],
        "missing_fields": result["missing_fields"],
        "feasibility_issues": result["feasibility_issues"],
        "validation_errors": result["validation_errors"],
    }
    user_profile = {
        field: profile_result["profile"][field]
        for field in PROFILE_FIELDS
        if field in profile_result["profile"]
    }
    updates: dict[str, Any] = {
        "current_node": "user",
        "user_profile": user_profile,
        "constraints": profile_result["constraints"],
        "profile_complete": profile_result["complete"],
        "profile_valid": profile_result["valid"],
        "revision_feedback": None,
        "waiting_for_user": False,
    }
    return merge_subgraph_updates(
        state,
        updates,
        subgraph="user",
        steps=["extract", "validate", "persist"],
    )


class UserGraph:
    """LangGraph facade for the User subgraph."""

    def __init__(self) -> None:
        self._graph = get_user_subgraph()

    def invoke(self, state: UserState, config: RunnableConfig) -> UserState:
        return self._graph.invoke(state, config)

    def invoke_from_orchestration(self, state: OrchestrationState, config: RunnableConfig) -> dict:
        return invoke_user_subgraph(state, config)
