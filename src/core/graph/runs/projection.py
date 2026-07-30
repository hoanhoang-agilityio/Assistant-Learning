"""Pure checkpoint -> status projection helpers.

Every function here is a pure function of a LangGraph snapshot/state: none of
them touch orchestrator instance state (verified: zero ``self.`` references in
the block they were moved from). That is what makes them safe to test in
isolation, which they were not while buried at the bottom of service.py.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from core.graph.runs.models import RunLifecycleStatus
from core.shared.profile.labels import format_missing_profile_prompt
from core.vfs import VFS


def _resolve_display_node(
    state: dict[str, Any],
    next_nodes: tuple[str, ...],
    lifecycle: RunLifecycleStatus,
) -> str:
    """Return the node the UI should show as the active pipeline step.

    While a run is in flight, LangGraph checkpoints only update when a node
    finishes, so ``state["current_node"]`` lags behind the subgraph that is
    actually executing. Prefer ``next_nodes[0]`` in that case.
    """
    if lifecycle == "running" and next_nodes:
        return next_nodes[0]
    return str(state.get("current_node", "supervisor"))


def _resolve_lifecycle_status(
    state: dict[str, Any],
    next_nodes: tuple[str, ...],
    interrupts: tuple[Any, ...] = (),
) -> RunLifecycleStatus:
    if state.get("refusal_message") or state.get("run_complete") and state.get("refusal_message"):
        return "refused"
    if state.get("approval_status") == "rejected" and not next_nodes:
        return "completed"
    if state.get("approval_status") == "approved" and state.get("final_artifact_path"):
        return "completed"
    if (
        state.get("approval_status") == "approved"
        and not next_nodes
        and state.get("current_node") == "persist"
    ):
        return "completed"
    # `next_nodes == ("user",)` is ambiguous on its own: LangGraph reports it both when the
    # User subgraph is genuinely paused mid-interrupt() *and*, transiently, the instant
    # before "user" starts executing (it's a regular node, not a static interrupt_before
    # gate like "hitl"). Only a populated `interrupts` list means it's durably paused.
    if (
        next_nodes == ("hitl",)
        or (next_nodes == ("user",) and interrupts)
        or (state.get("waiting_for_user") and state.get("current_node") != "persist")
    ):
        return "waiting_hitl"
    if state.get("current_node") == "persist" and not next_nodes:
        return "completed"
    if next_nodes:
        return "running"
    if state.get("run_complete") and state.get("final_response") and not next_nodes:
        return "completed"
    if state.get("final_artifact_path"):
        return "completed"
    return "running"


def _collect_interrupts(snapshot: Any) -> tuple[Any, ...]:
    """Flatten every pending interrupt across a graph snapshot's tasks."""
    return tuple(interrupt for task in snapshot.tasks for interrupt in (task.interrupts or ()))


def _read_final_plan(state: dict[str, Any]) -> str | None:
    workspace_path = state.get("workspace_path")
    if not workspace_path:
        return None
    vfs = VFS.for_run(Path(workspace_path))
    if vfs.exists("final/final_plan.md"):
        return vfs.read("final/final_plan.md")
    if vfs.exists("fitness/final_plan.md"):
        return vfs.read("fitness/final_plan.md")
    return None


def _extract_profile_form_payload(interrupts: tuple[Any, ...]) -> dict[str, Any] | None:
    for item in interrupts:
        value = getattr(item, "value", None)
        if isinstance(value, dict) and value.get("type") == "profile_form":
            return value
    return None


def _resolve_hitl_context(
    state: dict[str, Any],
    next_nodes: tuple[str, ...],
    interrupts: tuple[Any, ...] = (),
) -> tuple[str | None, str | None]:
    if next_nodes == ("user",):
        # Same ambiguity as _resolve_lifecycle_status: next_nodes == ("user",) alone
        # doesn't mean paused -- it can also be a transient "about to run" read, since
        # "user" is a regular node, not a static interrupt_before gate. Only report
        # "profile_form" when there's an actual recorded interrupt.
        payload = _extract_profile_form_payload(interrupts)
        if payload is not None:
            missing_fields = payload.get("missing_fields") or []
            if missing_fields:
                return "profile_form", format_missing_profile_prompt(missing_fields)
            return "profile_form", "Please review and submit your profile."
        return None, None

    if state.get("approval_status") in {"rejected", "approved"}:
        return None, None
    if next_nodes != ("hitl",) and not state.get("waiting_for_user"):
        return None, None

    workspace_path = state.get("workspace_path")
    if not workspace_path:
        return None, "Waiting for user input."

    draft_plan = _read_final_plan(state)
    if draft_plan:
        preview = draft_plan[:500]
        if state.get("verification_passed"):
            return (
                "approval",
                f"Review the draft fitness plan. Approve to save, or reject with feedback to replan.\n\n{preview}",
            )
        return (
            "approval",
            "A draft plan is ready for review. Verification did not fully pass, but you can "
            f"approve, reject, or refresh after changes. Preview:\n\n{preview}",
        )

    return "approval", "Waiting for approval or clarification."
