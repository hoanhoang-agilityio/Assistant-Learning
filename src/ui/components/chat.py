"""Chat messages, input handling, and HITL UI."""

from __future__ import annotations

from typing import Any

import httpx
import streamlit as st

from ui.api_client import (
    create_run,
    get_run,
    poll_run_until_settled,
    resume_run,
)


def _clarification_prompt(status: dict[str, Any]) -> str:
    return status.get("hitl_message") or "Please share a few more details about yourself."


def _pipeline_step(status: dict[str, Any]) -> str:
    return status.get("current_node") or "supervisor"


def _write_pipeline_step(
    status_container: Any,
    status: dict[str, Any],
    *,
    last_step: str | None,
) -> str:
    """Write a pipeline step line only when the active step changes."""
    step = _pipeline_step(status)
    status_container.update(label=f"Running pipeline… — {step}")
    if step != last_step:
        status_container.write(f"Current step: **{step}**")
    return step


def _format_assistant_status_message(status: dict[str, Any]) -> str:
    run_status = status.get("status")
    if run_status == "failed":
        return status.get("error_message") or "Run failed."
    if run_status == "waiting_hitl":
        hitl_type = status.get("hitl_type") or "approval"
        if hitl_type == "clarification":
            return _clarification_prompt(status)
        draft = status.get("final_plan")
        if draft:
            return draft
        return status.get("hitl_message") or ""
    if run_status == "completed":
        final_plan = status.get("final_plan")
        if final_plan:
            return final_plan
        return "Run completed but no final plan artifact was found."
    return "The plan is still being generated. Please wait a moment…"


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
        with st.status("Running pipeline…", expanded=True) as pipeline_status:
            last_step = _write_pipeline_step(
                pipeline_status,
                status,
                last_step=None,
            )

            def handle_poll_progress(status_update: dict[str, Any]) -> None:
                nonlocal last_step
                last_step = _write_pipeline_step(
                    pipeline_status,
                    status_update,
                    last_step=last_step,
                )

            settled = poll_run_until_settled(
                client,
                run_id,
                on_progress=handle_poll_progress,
            )
            pipeline_status.update(label="Pipeline finished", state="complete")

        st.session_state.run_status = settled
        st.session_state.messages = _rebuild_messages_from_run(settled)
        _update_run_history_status(run_id, settled.get("status", "unknown"))
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
    if run_status in {"failed", "waiting_hitl", "completed", "running"}:
        content = _format_assistant_status_message(status)
        if content:
            messages.append({"role": "assistant", "content": content})
    return messages


def _assistant_message_from_status(status: dict[str, Any]) -> str:
    return _format_assistant_status_message(status)


def _add_to_run_history(run_id: str, query: str, status: str) -> None:
    entry = {"run_id": run_id, "query": query, "status": status}
    history: list[dict[str, str]] = st.session_state.run_history
    for index, item in enumerate(history):
        if item["run_id"] == run_id:
            history[index] = entry
            return
    history.append(entry)


def _update_run_history_status(run_id: str, status: str) -> None:
    for item in st.session_state.run_history:
        if item["run_id"] == run_id:
            item["status"] = status
            return


def render_messages(messages: list[dict[str, str]]) -> None:
    for message in messages:
        with st.chat_message(message["role"]):
            st.markdown(message["content"])


def render_hitl_actions(
    client: httpx.Client,
    run_id: str,
    status: dict[str, Any],
) -> None:
    """Approval-only HITL controls. Clarification uses the chat input."""
    if not status.get("verification_passed"):
        st.markdown(
            '<div class="pt-hitl-panel"><p>Verification did not fully pass. '
            "You can approve to save the plan or reject to start over.</p></div>",
            unsafe_allow_html=True,
        )

    action_cols = st.columns(2)
    if action_cols[0].button("Approve plan", type="primary", key="approve_plan"):
        with st.status("Persisting approved plan…", expanded=True) as approve_status:
            last_step: str | None = None

            def handle_approve_progress(status_update: dict[str, Any]) -> None:
                nonlocal last_step
                step = _pipeline_step(status_update)
                approve_status.update(label=f"Finalizing run… — {step}")
                if step != last_step:
                    approve_status.write(f"Current step: **{step}**")
                    last_step = step

            updated = resume_run(
                client,
                run_id,
                user_response="approve",
                approval_status="approved",
                on_progress=handle_approve_progress,
            )
        st.session_state.run_status = updated
        st.session_state.messages.append(
            {"role": "user", "content": "Approved the plan."},
        )
        st.session_state.messages.append(
            {
                "role": "assistant",
                "content": _assistant_message_from_status(updated),
            }
        )
        _update_run_history_status(run_id, updated.get("status", "unknown"))
        st.rerun()
    if action_cols[1].button("Reject plan", key="reject_plan"):
        updated = resume_run(
            client,
            run_id,
            user_response="reject",
            approval_status="rejected",
        )
        st.session_state.run_status = updated
        st.session_state.messages.append(
            {"role": "user", "content": "Rejected the plan."},
        )
        st.session_state.messages.append(
            {
                "role": "assistant",
                "content": _assistant_message_from_status(updated),
            }
        )
        _update_run_history_status(run_id, updated.get("status", "unknown"))
        st.rerun()


def _handle_clarification(client: httpx.Client, run_id: str, query: str) -> None:
    st.session_state.messages.append({"role": "user", "content": query})
    try:
        with st.status("Resuming run after clarification…", expanded=True) as resume_status:
            last_step: str | None = None

            def handle_resume_progress(status_update: dict[str, Any]) -> None:
                nonlocal last_step
                step = _pipeline_step(status_update)
                resume_status.update(label=f"Resuming run… — {step}")
                if step != last_step:
                    resume_status.write(f"Current step: **{step}**")
                    last_step = step

            updated = resume_run(
                client,
                run_id,
                user_response=query,
                on_progress=handle_resume_progress,
            )
        st.session_state.run_status = updated
        st.session_state.messages.append(
            {
                "role": "assistant",
                "content": _assistant_message_from_status(updated),
            }
        )
        _update_run_history_status(run_id, updated.get("status", "unknown"))
    except httpx.TimeoutException:
        st.session_state.messages.append(
            {
                "role": "assistant",
                "content": "Still processing your clarification. Please wait a moment…",
            },
        )
    except httpx.HTTPError as exc:
        st.session_state.messages.append(
            {"role": "assistant", "content": f"Failed to submit clarification: {exc}"},
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

    if status and status.get("status") == "running" and run_id:
        sync_active_run_if_needed(client)
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
        st.session_state.run_id = new_run_id
        poll_status = created

        with st.status("Running pipeline…", expanded=True) as pipeline_status:
            last_step = _write_pipeline_step(
                pipeline_status,
                created,
                last_step=None,
            )

            def handle_poll_progress(status_update: dict[str, Any]) -> None:
                nonlocal poll_status, last_step
                poll_status = status_update
                last_step = _write_pipeline_step(
                    pipeline_status,
                    status_update,
                    last_step=last_step,
                )

            settled = poll_run_until_settled(
                client,
                new_run_id,
                on_progress=handle_poll_progress,
            )
            pipeline_status.update(label="Pipeline finished", state="complete")

        st.session_state.run_status = settled
        assistant_content = _assistant_message_from_status(settled)
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
                    "content": _assistant_message_from_status(poll_status),
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
            {"role": "assistant", "content": f"Failed to start run: {exc}"},
        )
    finally:
        st.session_state.is_processing = False


def load_run_from_history(client: httpx.Client, run_id: str) -> None:
    status = get_run(client, run_id)
    st.session_state.run_id = run_id
    st.session_state.run_status = status
    st.session_state.messages = _rebuild_messages_from_run(status)
    if status.get("status") == "running":
        sync_active_run_if_needed(client)
