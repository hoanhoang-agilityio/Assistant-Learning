"""Chat messages, input handling, and HITL UI."""

from __future__ import annotations

import json
import time
from collections.abc import Callable
from typing import Any

import httpx
import streamlit as st

from ui.api_client import (
    continue_run,
    create_run,
    get_run,
    resume_run,
    stream_run_until_settled,
)
from ui.copy import (
    APPROVAL_STATUS_COPY,
    HITL_TYPE_COPY,
    ROUTE_DECISION_COPY,
    STATUS_COPY,
    step_display,
)


def _clarification_prompt(status: dict[str, Any]) -> str:
    return status.get("hitl_message") or "Mind sharing a few more details about yourself?"


def _format_thinking_label(elapsed_seconds: float) -> str:
    """ "Thought for Ns" -- rounded, minimum 1s so a near-instant first step
    never reads as "Thought for 0s"."""
    return f"Thought for {max(1, round(elapsed_seconds))}s"


def _timeline_header_html(label: str, *, active: bool) -> str:
    dot_class = "pt-timeline__header-dot"
    if active:
        dot_class += " pt-timeline__header-dot--active"
    return (
        '<div class="pt-timeline__header">'
        f'<span class="{dot_class}"></span>'
        f'<span class="pt-timeline__header-text">{label}</span>'
        "</div>"
    )


def _timeline_row_html(step_id: str, *, active: bool, animate: bool) -> str:
    text = step_display(step_id)[1]
    icon = (
        '<span class="pt-timeline__icon pt-timeline__icon--active"></span>'
        if active
        else '<span class="pt-timeline__icon pt-timeline__icon--done">✓</span>'
    )
    row_class = "pt-timeline__row pt-timeline__row--enter" if animate else "pt-timeline__row"
    return f'<div class="{row_class}">{icon}<span class="pt-timeline__text">{text}</span></div>'


def _timeline_html(
    *,
    thinking_label: str | None,
    thinking_in_progress: bool,
    completed_steps: list[str],
    active_step: str | None,
) -> str:
    """Build the full growing execution timeline: a frozen "Thinking…"/
    "Thought for Ns" header (omitted entirely when `thinking_label` is None --
    a run rebuilt from a status snapshot with no client-side timing
    available) followed by one row per step seen so far. Exactly one row
    (the last, when `active_step` is set) is ever the active spinner; every
    other row is a checkmarked completed step and is never removed. Only the
    single most-recently-changed row gets the enter animation -- see
    style.css's .pt-timeline for why.
    """
    parts: list[str] = []
    if thinking_label is not None:
        parts.append(_timeline_header_html(thinking_label, active=thinking_in_progress))
    rows = [*completed_steps, *([active_step] if active_step is not None else [])]
    last_index = len(rows) - 1
    for index, step_id in enumerate(rows):
        parts.append(
            _timeline_row_html(
                step_id,
                active=active_step is not None and index == last_index,
                animate=index == last_index,
            )
        )
    return f'<div class="pt-timeline">{"".join(parts)}</div>'


class TimelineTracker:
    """Drives one run's live execution timeline into a single placeholder.

    Exactly one step is ever the active (spinning) row; every prior step it
    supersedes becomes a permanent checkmarked row -- completed rows
    accumulate for the rest of the run instead of being replaced. Call
    on_progress() as the on_progress callback for stream_run_until_settled/
    resume_run/continue_run, then finish() once the run settles: it converts
    the last active row to completed and returns (steps, thinking_seconds)
    for the caller to attach to the persisted chat message (see
    render_messages) so the timeline stays visible in history, not just
    during the live run.
    """

    def __init__(self, placeholder: Any, *, existing_steps: list[str] | None = None) -> None:
        self._placeholder = placeholder
        self._started_at = time.monotonic()
        self._thinking_elapsed: float | None = None
        self._completed_steps: list[str] = list(existing_steps or [])
        self._active_step: str | None = None
        self._shown: set[str] = set(self._completed_steps)
        # A run picked up already in progress (page refresh, reconnect) has no
        # meaningful "thinking" moment from this session's point of view --
        # whatever happened, happened before this tracker existed -- so it
        # never shows the "Thinking…"/"Thought for Ns" header at all, only the
        # (possibly already non-empty) step checklist.
        self._resumed = bool(existing_steps)
        self._render()

    def _render(self) -> None:
        if self._resumed:
            label = None
        elif self._thinking_elapsed is not None:
            label = _format_thinking_label(self._thinking_elapsed)
        else:
            label = "Thinking..."
        self._placeholder.markdown(
            _timeline_html(
                thinking_label=label,
                thinking_in_progress=(not self._resumed) and self._thinking_elapsed is None,
                completed_steps=self._completed_steps,
                active_step=self._active_step,
            ),
            unsafe_allow_html=True,
        )

    def on_progress(self, status_update: dict[str, Any]) -> None:
        steps = status_update.get("steps") or []
        if not steps:
            return
        new_step = steps[-1]
        # Global dedup (not just consecutive) mirrors append_pipeline_steps
        # on the backend -- a retried node (e.g. a second fitness_planner
        # attempt) reports the same step id again, and RunStatus.steps itself
        # never lists it twice, so the live timeline must not either or it
        # would show one extra row than the persisted history does.
        if new_step in self._shown:
            return
        self._shown.add(new_step)
        if self._thinking_elapsed is None:
            self._thinking_elapsed = time.monotonic() - self._started_at
        if self._active_step is not None:
            self._completed_steps.append(self._active_step)
        self._active_step = new_step
        self._render()

    def finish(
        self, authoritative_steps: list[str] | None = None
    ) -> tuple[list[str], float | None]:
        """Convert the final active row to completed and render once more.

        Prefers the server's own final `steps` list (from the settled
        RunStatus) over what this tracker observed live, so the timeline that
        ends up persisted into chat history is guaranteed to match what a
        fresh page load would rebuild from that same run.
        """
        if authoritative_steps is not None:
            final_steps = authoritative_steps
        else:
            final_steps = [
                *self._completed_steps,
                *([self._active_step] if self._active_step else []),
            ]
        self._completed_steps = final_steps
        self._active_step = None
        self._render()
        return final_steps, self._thinking_elapsed


def attach_timeline(status: dict[str, Any], tracker: TimelineTracker) -> dict[str, Any]:
    """Finalize `tracker` and stash its result onto a copy of `status` under
    UI-only keys (never sent back to the API -- see api_client.py, nothing
    there serializes a RunStatus dict wholesale as a request body).

    Lets a `run_guarded_backend_action` action (do_approve, do_reject, etc.,
    which must return a single dict) carry the timeline alongside the real
    RunStatus payload, so the matching on_success handler can pull it back
    out via build_timeline_message and attach it to the persisted chat message.
    """
    steps, thinking_seconds = tracker.finish(status.get("steps"))
    return {**status, "_timeline_steps": steps, "_timeline_thinking_seconds": thinking_seconds}


def build_timeline_message(status: dict[str, Any], content: str) -> dict[str, Any]:
    """Build an assistant message dict, attaching the timeline attach_timeline
    stashed on `status` (if any) so render_messages redraws it as part of
    chat history from now on, not just during the live run."""
    message: dict[str, Any] = {"role": "assistant", "content": content}
    steps = status.get("_timeline_steps")
    if steps:
        message["steps"] = steps
        message["thinking_seconds"] = status.get("_timeline_thinking_seconds")
    return message


def _format_assistant_status_message(status: dict[str, Any]) -> str:
    run_status = status.get("status")
    approval_status = status.get("approval_status")
    if approval_status == "rejected":
        return (
            f"🙅 {APPROVAL_STATUS_COPY['rejected']} "
            "Send a new message whenever you're ready for a different plan."
        )
    if run_status == "running" and status.get("route_decision") == "REPLAN":
        return f"🔄 {ROUTE_DECISION_COPY['REPLAN']}"
    if approval_status == "approved" and run_status == "completed":
        final_plan = status.get("final_plan")
        if final_plan:
            return f"✅ Your plan is approved and saved. Here it is:\n\n{final_plan}"
        return "✅ Your plan is approved and saved."
    if approval_status == "approved" and run_status == "running":
        return f"💾 {APPROVAL_STATUS_COPY['approved']}"
    if run_status == "failed":
        icon, _ = STATUS_COPY["failed"]
        error = status.get("error_message") or "The run hit a snag. Please try again."
        return f"{icon} {error}"
    if run_status == "refused":
        icon, fallback = STATUS_COPY["refused"]
        return f"{icon} {status.get('refusal_message') or fallback}"
    if run_status == "waiting_hitl":
        hitl_type = status.get("hitl_type") or "approval"
        if hitl_type == "clarification":
            return f"🙋 {_clarification_prompt(status)}"
        draft = status.get("final_plan")
        if draft:
            return draft
        return status.get("hitl_message") or HITL_TYPE_COPY.get(hitl_type, "")
    if run_status == "completed":
        final_plan = status.get("final_plan")
        if final_plan:
            return final_plan
        return "✅ All done, but I couldn't find the final plan artifact."
    _, message = STATUS_COPY.get(
        run_status, ("⏳", "The plan is still being generated. Please wait a moment…")
    )
    return message


def set_active_run(run_id: str | None) -> None:
    """Track which conversation is active, including in the URL.

    Only the single active run_id is persisted (as a query param) so a page
    refresh can restore it via ``load_run_from_history``. This does not persist
    the full run_history list, so switching between multiple past
    conversations after a refresh isn't supported yet.
    """
    st.session_state.run_id = run_id
    if run_id:
        st.query_params["run_id"] = run_id
    else:
        st.query_params.pop("run_id", None)


def sync_active_run_if_needed(client: httpx.Client) -> bool:
    """Pick up an in-progress run's live event stream until it settles (no manual refresh required)."""
    run_id = st.session_state.run_id
    status = st.session_state.run_status
    if not run_id or not status or status.get("status") != "running":
        return False
    if st.session_state.is_processing:
        return False

    st.session_state.is_processing = True
    try:
        row = st.empty()
        tracker = TimelineTracker(row, existing_steps=status.get("steps"))

        settled = stream_run_until_settled(
            client,
            run_id,
            on_progress=tracker.on_progress,
        )
        tracker.finish(settled.get("steps"))

        st.session_state.run_status = settled
        st.session_state.messages = _rebuild_messages_from_run(settled)
        update_run_history_status(run_id, settled.get("status", "unknown"))
        return settled.get("status") != "running"
    except httpx.TimeoutException:
        latest = get_run(client, run_id)
        st.session_state.run_status = latest
        st.session_state.messages = _rebuild_messages_from_run(latest)
        return latest.get("status") != "running"
    finally:
        st.session_state.is_processing = False


def _rebuild_messages_from_run(status: dict[str, Any]) -> list[dict[str, Any]]:
    messages: list[dict[str, Any]] = []
    query = status.get("query")
    if query:
        messages.append({"role": "user", "content": query})

    run_status = status.get("status")
    if run_status in {"failed", "waiting_hitl", "completed", "running", "refused"}:
        content = _format_assistant_status_message(status)
        if content:
            message: dict[str, Any] = {"role": "assistant", "content": content}
            # No client-side thinking_seconds available when rebuilding from a
            # status snapshot (page reload, picking up someone else's run) --
            # the timeline still renders from the server's own `steps`, just
            # without a "Thought for Ns" header (see render_messages).
            steps = status.get("steps") or []
            if steps:
                message["steps"] = steps
            messages.append(message)
    return messages


def assistant_message_from_status(status: dict[str, Any]) -> str:
    return _format_assistant_status_message(status)


def _add_to_run_history(run_id: str, query: str, status: str) -> None:
    entry = {"run_id": run_id, "query": query, "status": status}
    history: list[dict[str, str]] = st.session_state.run_history
    for index, item in enumerate(history):
        if item["run_id"] == run_id:
            history[index] = entry
            return
    history.append(entry)


def update_run_history_status(run_id: str, status: str) -> None:
    for item in st.session_state.run_history:
        if item["run_id"] == run_id:
            item["status"] = status
            return


_AVATARS = {"user": "🙂", "assistant": "🏋️"}


def run_guarded_backend_action(
    action: Callable[[], dict[str, Any]],
    *,
    on_success: Callable[[dict[str, Any]], None],
    timeout_message: str,
    error_prefix: str,
    rerun_on_settle: bool = False,
) -> None:
    """Run a backend-calling action; apply `on_success` to its result, or
    append a friendly assistant message on failure -- never let a network
    error, a malformed/unparseable response, or a backend failure crash the
    script with a raw traceback and no reply.

    The one shared shape behind every button/form submission that calls the
    backend and then updates run_status/messages/run_history. Previously this
    existed correctly, but duplicated, in _handle_plan_change/_handle_clarification,
    and was entirely missing from render_hitl_actions (approve/reject) and
    render_profile_form (profile submission) -- the two most consequential
    user actions in the app, where any hiccup crashed the whole session with
    no user-facing message at all.
    """
    try:
        result = action()
    except httpx.TimeoutException:
        st.session_state.messages.append({"role": "assistant", "content": timeout_message})
        if rerun_on_settle:
            st.rerun()
        return
    except (httpx.HTTPError, json.JSONDecodeError, KeyError) as exc:
        st.session_state.messages.append(
            {"role": "assistant", "content": f"⚠️ {error_prefix}: {exc}"}
        )
        if rerun_on_settle:
            st.rerun()
        return
    on_success(result)
    if rerun_on_settle:
        st.rerun()


def render_messages(messages: list[dict[str, Any]]) -> None:
    for message in messages:
        with st.chat_message(message["role"], avatar=_AVATARS.get(message["role"])):
            steps = message.get("steps")
            if steps:
                thinking_seconds = message.get("thinking_seconds")
                thinking_label = (
                    _format_thinking_label(thinking_seconds)
                    if thinking_seconds is not None
                    else None
                )
                st.markdown(
                    _timeline_html(
                        thinking_label=thinking_label,
                        thinking_in_progress=False,
                        completed_steps=steps,
                        active_step=None,
                    ),
                    unsafe_allow_html=True,
                )
            st.markdown(message["content"])


def render_hitl_actions(
    client: httpx.Client,
    run_id: str,
    status: dict[str, Any],
) -> None:
    """HITL controls for final plan approval."""
    if status.get("approval_status") in {"rejected", "approved"}:
        return

    hitl_type = status.get("hitl_type") or "approval"
    if hitl_type == "clarification":
        return

    st.markdown(
        f'<div class="pt-hitl-banner">🙋 <span>{HITL_TYPE_COPY.get(hitl_type, "Your plan is ready for review.")}</span></div>',
        unsafe_allow_html=True,
    )
    st.markdown('<div class="pt-hitl-actions-marker"></div>', unsafe_allow_html=True)
    action_cols = st.columns([1, 1, 8])
    if action_cols[0].button("✅ Approve", type="primary", key="approve_plan"):

        def do_approve() -> dict[str, Any]:
            row = st.empty()
            tracker = TimelineTracker(row)
            updated = resume_run(
                client,
                run_id,
                decision_type="approve",
                on_progress=tracker.on_progress,
            )
            return attach_timeline(updated, tracker)

        def on_approve_success(updated: dict[str, Any]) -> None:
            st.session_state.run_status = updated
            st.session_state.messages.append(
                {"role": "user", "content": "Approved the plan."},
            )
            st.session_state.messages.append(
                build_timeline_message(updated, assistant_message_from_status(updated))
            )
            update_run_history_status(run_id, updated.get("status", "unknown"))

        run_guarded_backend_action(
            do_approve,
            on_success=on_approve_success,
            timeout_message=(
                "⏳ Still saving your approval — this is taking a little longer than "
                "usual. Please wait a moment…"
            ),
            error_prefix="Couldn't save your approval",
            rerun_on_settle=True,
        )

    if action_cols[1].button("✋ Reject", key="reject_plan"):

        def do_reject() -> dict[str, Any]:
            row = st.empty()
            tracker = TimelineTracker(row)
            updated = resume_run(
                client,
                run_id,
                decision_type="reject",
                message="Rejected the plan.",
            )
            return attach_timeline(updated, tracker)

        def on_reject_success(updated: dict[str, Any]) -> None:
            st.session_state.run_status = updated
            st.session_state.messages.append(
                {"role": "user", "content": "Rejected the plan."},
            )
            st.session_state.messages.append(
                build_timeline_message(updated, assistant_message_from_status(updated))
            )
            update_run_history_status(run_id, updated.get("status", "unknown"))

        run_guarded_backend_action(
            do_reject,
            on_success=on_reject_success,
            timeout_message=(
                "⏳ Still rejecting the plan — this is taking a little longer than "
                "usual. Please wait a moment…"
            ),
            error_prefix="Couldn't reject the plan",
            rerun_on_settle=True,
        )


def _can_change_plan_in_conversation(status: dict[str, Any]) -> bool:
    run_status = status.get("status")
    if run_status == "completed":
        return True
    if run_status != "waiting_hitl":
        return False
    hitl_type = status.get("hitl_type") or "approval"
    return hitl_type == "approval" and status.get("approval_status") not in {
        "rejected",
        "approved",
    }


def _handle_plan_change(client: httpx.Client, run_id: str, query: str) -> None:
    st.session_state.messages.append({"role": "user", "content": query})

    def do_call() -> dict[str, Any]:
        row = st.empty()
        tracker = TimelineTracker(row)
        updated = continue_run(
            client,
            run_id,
            message=query,
            on_progress=tracker.on_progress,
        )
        return attach_timeline(updated, tracker)

    def on_success(updated: dict[str, Any]) -> None:
        st.session_state.run_status = updated
        st.session_state.messages.append(
            build_timeline_message(updated, assistant_message_from_status(updated))
        )
        update_run_history_status(run_id, updated.get("status", "unknown"))

    run_guarded_backend_action(
        do_call,
        on_success=on_success,
        timeout_message=(
            "⏳ Still reworking your plan — this is taking a little longer than "
            "usual. Please wait a moment…"
        ),
        error_prefix="Couldn't submit your plan changes",
    )


def _handle_clarification(client: httpx.Client, run_id: str, query: str) -> None:
    st.session_state.messages.append({"role": "user", "content": query})

    def do_call() -> dict[str, Any]:
        row = st.empty()
        tracker = TimelineTracker(row)
        updated = resume_run(
            client,
            run_id,
            user_response=query,
            on_progress=tracker.on_progress,
        )
        return attach_timeline(updated, tracker)

    def on_success(updated: dict[str, Any]) -> None:
        st.session_state.run_status = updated
        st.session_state.messages.append(
            build_timeline_message(updated, assistant_message_from_status(updated))
        )
        update_run_history_status(run_id, updated.get("status", "unknown"))

    run_guarded_backend_action(
        do_call,
        on_success=on_success,
        timeout_message="⏳ Still working through your answer. Please wait a moment…",
        error_prefix="Couldn't submit your answer",
    )


def handle_user_input(
    client: httpx.Client,
    query: str,
    *,
    build_profile: Any,
) -> None:
    status = st.session_state.run_status
    run_id = st.session_state.run_id

    if status and status.get("status") == "waiting_hitl":
        hitl_type = status.get("hitl_type") or "approval"
        if hitl_type == "clarification" and run_id:
            _handle_clarification(client, run_id, query)
            return
        if hitl_type == "approval" and run_id:
            _handle_plan_change(client, run_id, query)
            return

    if run_id and status and _can_change_plan_in_conversation(status):
        _handle_plan_change(client, run_id, query)
        return

    if status and status.get("status") == "running" and run_id:
        sync_active_run_if_needed(client)
        st.session_state.messages.append({"role": "user", "content": query})
        st.session_state.messages.append(
            {
                "role": "assistant",
                "content": "⏳ Still putting your plan together — I'll be ready for changes as soon as it's done.",
            },
        )
        return

    st.session_state.messages = [{"role": "user", "content": query}]
    profile = build_profile()
    constraints_days = st.session_state.get("constraints_days", 4)
    constraints = {"days_per_week": constraints_days, "equipment": "gym"}
    poll_status: dict[str, Any] | None = None
    new_run_id: str | None = None
    tracker: TimelineTracker | None = None

    try:
        st.session_state.is_processing = True
        created = create_run(
            client,
            query=query,
            user_profile=profile,
            constraints=constraints,
        )
        new_run_id = created["run_id"]
        set_active_run(new_run_id)
        poll_status = created

        row = st.empty()
        tracker = TimelineTracker(row)

        def handle_progress(status_update: dict[str, Any]) -> None:
            # Keep poll_status's "steps" fresh (a full RunStatus dict, seeded
            # from `created`) for the httpx.TimeoutException fallback below --
            # status_update here only carries the accumulated step ids
            # streamed so far, not a full status, and poll_status must stay
            # full-shaped (assistant_message_from_status reads status/
            # approval_status/final_plan/etc., none of which a steps-only
            # dict has).
            nonlocal poll_status
            poll_status = {**poll_status, "steps": status_update["steps"]}
            tracker.on_progress(status_update)

        settled = stream_run_until_settled(
            client,
            new_run_id,
            on_progress=handle_progress,
        )
        settled = attach_timeline(settled, tracker)

        st.session_state.run_status = settled
        assistant_content = assistant_message_from_status(settled)
        st.session_state.messages.append(build_timeline_message(settled, assistant_content))
        _add_to_run_history(
            new_run_id,
            query,
            settled.get("status", "unknown"),
        )

    except httpx.TimeoutException:
        if poll_status is not None:
            if tracker is not None:
                poll_status = attach_timeline(poll_status, tracker)
            st.session_state.run_status = poll_status
            st.session_state.messages.append(
                build_timeline_message(poll_status, assistant_message_from_status(poll_status))
            )
            if new_run_id:
                _add_to_run_history(
                    new_run_id,
                    query,
                    poll_status.get("status", "running"),
                )
        st.session_state.pending_query = None
    except httpx.HTTPError as exc:
        st.session_state.messages.append(
            {"role": "assistant", "content": f"⚠️ Couldn't start your plan: {exc}"},
        )
    finally:
        st.session_state.is_processing = False


def load_run_from_history(client: httpx.Client, run_id: str) -> None:
    status = get_run(client, run_id)
    set_active_run(run_id)
    st.session_state.run_status = status
    st.session_state.messages = _rebuild_messages_from_run(status)
    if status.get("status") == "running":
        sync_active_run_if_needed(client)
