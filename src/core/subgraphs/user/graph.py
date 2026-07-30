from functools import lru_cache
from typing import Any

from langchain_core.runnables import RunnableConfig
from langgraph.graph import END, START, StateGraph
from langgraph.graph.state import CompiledStateGraph
from langgraph.types import interrupt

from core.agents.state import OrchestrationState
from core.shared.profile.goal_spec import derive_goal_spec
from core.shared.profile.store import load_run_profile
from core.subgraphs.user.state import UserState
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
        state["profile"],
        revision_feedback=state.get("revision_feedback"),
    )
    # apply_revision_overrides (inside extract_profile) stashes this as an internal marker
    # on the profile dict when the revision text explicitly named a training-frequency
    # target; pop it back off so it never reaches validation/persistence as a profile field.
    days_per_week_explicit = profile.pop("_days_per_week_explicit", False)
    return {
        "profile": profile,
        "days_per_week_explicit": days_per_week_explicit,
    }


def _validate_node(state: UserState) -> dict:
    # GoalSpec is derived exactly once here -- the sole node downstream of every place
    # `profile` can change (_extract_node, _form_node) -- and passed explicitly into
    # validate_profile_completeness rather than recomputed inside it.
    goal_spec = derive_goal_spec(state["profile"])
    completeness = validate_profile_completeness(state["profile"], goal_spec)
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
        query=state["fitness_query"],
        workspace_path=state["workspace_path"],
        revision_feedback=state.get("revision_feedback"),
        profile=load_run_profile(state["workspace_path"]),
        missing_fields=[],
        feasibility_issues=[],
        validation_errors=[],
        complete=False,
        valid=False,
        days_per_week_explicit=False,
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
    updates: dict[str, Any] = {
        "current_node": "user",
        "profile_complete": result["complete"],
        "profile_valid": result["valid"],
        "waiting_for_user": False,
        "days_per_week_explicit": result["days_per_week_explicit"],
    }
    # NOTE: revision_feedback is intentionally left untouched -- Planning also reads it
    # (to inform the plan-regeneration prompt), so it must survive past this subgraph even
    # though the profile-relevant parts of it have already been applied above.
    return merge_subgraph_updates(
        state,
        updates,
        subgraph="user",
        steps=["extract", "validate", "persist"],
    )
