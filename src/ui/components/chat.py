"""Chat messages, input handling, and HITL UI."""

from __future__ import annotations

import json
from collections.abc import Callable
from typing import Any

import httpx
import streamlit as st

from ui.api_client import (
    continue_run,
    create_run,
    get_run,
    poll_run_until_settled,
    resume_run,
)
from ui.copy import (
    APPROVAL_STATUS_COPY,
    HITL_TYPE_COPY,
    PHASE_ICONS,
    PHASE_LABELS,
    ROUTE_DECISION_COPY,
    STATUS_COPY,
    phase_color,
    phase_of,
    step_display,
)


def _clarification_prompt(status: dict[str, Any]) -> str:
    return status.get("hitl_message") or "Mind sharing a few more details about yourself?"


def _pipeline_step(status: dict[str, Any]) -> str:
    steps = status.get("steps") or []
    if steps:
        return steps[-1]
    return status.get("current_node") or "supervisor"


def _format_steps_trail(status: dict[str, Any]) -> str | None:
    """Friendly, deduped phase trail, e.g. '🗺️ Planning → 🔎 Researching → 🏋️ Building your plan'."""
    steps = status.get("steps") or []
    if not steps:
        return None
    phases: list[str] = []
    for step in steps:
        phase = phase_of(step)
        if not phases or phases[-1] != phase:
            phases.append(phase)
    trail = phases[-6:]
    return " → ".join(f"{PHASE_ICONS.get(p, '⚙️')} {PHASE_LABELS.get(p, p.title())}" for p in trail)


def write_pipeline_step(
    status_container: Any,
    status: dict[str, Any],
    *,
    last_step: str | None,
) -> str:
    """Write a friendly pipeline step line only when the active step changes."""
    step = _pipeline_step(status)
    icon, message = step_display(step)
    trail = _format_steps_trail(status)
    # expanded=True must be re-asserted on every update(), otherwise Streamlit
    # silently collapses the box back down on the very next label change —
    # which previously made the whole step trail invisible during a live run.
    status_container.update(label=f"{icon} {message}", expanded=True)
    if step != last_step:
        color = phase_color(step)
        status_container.markdown(
            f'<div class="pt-step" style="--pt-step-color:{color}">'
            f'<span class="pt-step__icon">{icon}</span>'
            f'<span class="pt-step__text">{message}</span></div>',
            unsafe_allow_html=True,
        )
        if trail:
            status_container.caption(f"Progress so far: {trail}")
    return step


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
    """Poll an in-progress run until it settles (no manual refresh required)."""
    run_id = st.session_state.run_id
    status = st.session_state.run_status
    if not run_id or not status or status.get("status") != "running":
        return False
    if st.session_state.is_processing:
        return False

    st.session_state.is_processing = True
    try:
        with st.status("🧭 Picking up where we left off…", expanded=True) as pipeline_status:
            last_step = write_pipeline_step(
                pipeline_status,
                status,
                last_step=None,
            )

            def handle_poll_progress(status_update: dict[str, Any]) -> None:
                nonlocal last_step
                last_step = write_pipeline_step(
                    pipeline_status,
                    status_update,
                    last_step=last_step,
                )

            settled = poll_run_until_settled(
                client,
                run_id,
                on_progress=handle_poll_progress,
            )
            pipeline_status.update(label="✅ All set!", state="complete")

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


def _rebuild_messages_from_run(status: dict[str, Any]) -> list[dict[str, str]]:
    messages: list[dict[str, str]] = []
    query = status.get("query")
    if query:
        messages.append({"role": "user", "content": query})

    run_status = status.get("status")
    if run_status in {"failed", "waiting_hitl", "completed", "running", "refused"}:
        content = _format_assistant_status_message(status)
        if content:
            messages.append({"role": "assistant", "content": content})
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


def render_messages(messages: list[dict[str, str]]) -> None:
    for message in messages:
        with st.chat_message(message["role"], avatar=_AVATARS.get(message["role"])):
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
            with st.status("💾 Saving your approved plan…", expanded=True) as approve_status:
                last_step = write_pipeline_step(approve_status, status, last_step=None)

                def handle_approve_progress(status_update: dict[str, Any]) -> None:
                    nonlocal last_step
                    last_step = write_pipeline_step(
                        approve_status,
                        status_update,
                        last_step=last_step,
                    )

                updated = resume_run(
                    client,
                    run_id,
                    decision_type="approve",
                    on_progress=handle_approve_progress,
                )
                approve_status.update(label="✅ Saved!", state="complete")
            return updated

        def on_approve_success(updated: dict[str, Any]) -> None:
            st.session_state.run_status = updated
            st.session_state.messages.append(
                {"role": "user", "content": "Approved the plan."},
            )
            st.session_state.messages.append(
                {
                    "role": "assistant",
                    "content": assistant_message_from_status(updated),
                }
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
            with st.status("🙅 Rejecting the plan…", expanded=False) as reject_status:
                updated = resume_run(
                    client,
                    run_id,
                    decision_type="reject",
                    message="Rejected the plan.",
                )
                reject_status.update(label="🙅 Plan rejected", state="complete")
            return updated

        def on_reject_success(updated: dict[str, Any]) -> None:
            st.session_state.run_status = updated
            st.session_state.messages.append(
                {"role": "user", "content": "Rejected the plan."},
            )
            st.session_state.messages.append(
                {
                    "role": "assistant",
                    "content": assistant_message_from_status(updated),
                }
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
        with st.status(
            "🔄 Reworking your plan with your feedback…", expanded=True
        ) as revision_status:
            last_step: str | None = None

            def handle_revision_progress(status_update: dict[str, Any]) -> None:
                nonlocal last_step
                last_step = write_pipeline_step(
                    revision_status,
                    status_update,
                    last_step=last_step,
                )

            updated = continue_run(
                client,
                run_id,
                message=query,
                on_progress=handle_revision_progress,
            )
            revision_status.update(label="✅ Updated!", state="complete")
        return updated

    def on_success(updated: dict[str, Any]) -> None:
        st.session_state.run_status = updated
        st.session_state.messages.append(
            {
                "role": "assistant",
                "content": assistant_message_from_status(updated),
            }
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
        with st.status("🙋 Thanks! Picking up where we left off…", expanded=True) as resume_status:
            last_step: str | None = None

            def handle_resume_progress(status_update: dict[str, Any]) -> None:
                nonlocal last_step
                last_step = write_pipeline_step(
                    resume_status,
                    status_update,
                    last_step=last_step,
                )

            updated = resume_run(
                client,
                run_id,
                user_response=query,
                on_progress=handle_resume_progress,
            )
            resume_status.update(label="✅ Got it!", state="complete")
        return updated

    def on_success(updated: dict[str, Any]) -> None:
        st.session_state.run_status = updated
        st.session_state.messages.append(
            {
                "role": "assistant",
                "content": assistant_message_from_status(updated),
            }
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

        with st.status("👋 Got it — let's build your plan…", expanded=True) as pipeline_status:
            last_step = write_pipeline_step(
                pipeline_status,
                created,
                last_step=None,
            )

            def handle_poll_progress(status_update: dict[str, Any]) -> None:
                nonlocal poll_status, last_step
                poll_status = status_update
                last_step = write_pipeline_step(
                    pipeline_status,
                    status_update,
                    last_step=last_step,
                )

            settled = poll_run_until_settled(
                client,
                new_run_id,
                on_progress=handle_poll_progress,
            )
            pipeline_status.update(label="✅ All set!", state="complete")

        st.session_state.run_status = settled
        assistant_content = assistant_message_from_status(settled)
        st.session_state.messages.append(
            {"role": "assistant", "content": assistant_content},
        )
        _add_to_run_history(
            new_run_id,
            query,
            settled.get("status", "unknown"),
        )

    except httpx.TimeoutException:
        if poll_status is not None:
            st.session_state.run_status = poll_status
            st.session_state.messages.append(
                {
                    "role": "assistant",
                    "content": assistant_message_from_status(poll_status),
                }
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
