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
    return (
        f"Run is still in progress (status: {run_status}). Use **Refresh status** in the sidebar."
    )


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


def _render_hitl_form(
    client: httpx.Client,
    run_id: str,
    status: dict[str, Any],
    *,
    skip_draft: bool = False,
) -> None:
    hitl_type = status.get("hitl_type") or "approval"

    if hitl_type == "clarification":
        st.info(_clarification_prompt(status))
        clarification = st.text_area("Your clarification", key="hitl_clarification_input")
        if st.button("Submit clarification", key="submit_clarification"):
            updated = resume_run(client, run_id, user_response=clarification)
            st.session_state.run_status = updated
            st.session_state.messages.append(
                {"role": "user", "content": clarification},
            )
            st.session_state.messages.append(
                {
                    "role": "assistant",
                    "content": _assistant_message_from_status(updated),
                }
            )
            _update_run_history_status(run_id, updated.get("status", "unknown"))
            st.rerun()
        return

    if not skip_draft:
        draft = status.get("final_plan")
        if draft:
            st.subheader("Draft fitness plan")
            st.markdown(draft)
        else:
            st.warning(
                "No draft plan was returned by the API yet. "
                "Use **Refresh status** in the sidebar — the run may still be writing artifacts."
            )

    if not status.get("verification_passed"):
        st.warning(
            "Verification did not fully pass yet. You can still approve to save the plan, "
            "or reject to start over."
        )

    action_cols = st.columns(2)
    if action_cols[0].button("Approve", type="primary", key="approve_plan"):
        updated = resume_run(
            client,
            run_id,
            user_response="approve",
            approval_status="approved",
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
    if action_cols[1].button("Reject", key="reject_plan"):
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


def render_hitl_form(client: httpx.Client, run_id: str, status: dict[str, Any]) -> None:
    _render_hitl_form(client, run_id, status, skip_draft=True)


def _handle_clarification(client: httpx.Client, run_id: str, query: str) -> None:
    st.session_state.messages.append({"role": "user", "content": query})
    try:
        updated = resume_run(client, run_id, user_response=query)
        st.session_state.run_status = updated
        st.session_state.messages.append(
            {
                "role": "assistant",
                "content": _assistant_message_from_status(updated),
            }
        )
        _update_run_history_status(run_id, updated.get("status", "unknown"))
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

    if status and status.get("status") == "running":
        st.warning("A run is still in progress. Use **Refresh status** in the sidebar.")
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
            current_node = created.get("current_node") or "supervisor"
            pipeline_status.write(f"Current step: **{current_node}**")

            def handle_poll_progress(status_update: dict[str, Any]) -> None:
                nonlocal poll_status
                poll_status = status_update
                node = status_update.get("current_node") or "supervisor"
                pipeline_status.update(label=f"Running pipeline… — {node}")
                pipeline_status.write(f"Current step: **{node}**")

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

        if settled.get("status") == "failed":
            st.error(settled.get("error_message") or "Run failed.")
        elif settled.get("status") == "waiting_hitl":
            hitl_type = settled.get("hitl_type") or "approval"
            if hitl_type == "clarification":
                st.info(_clarification_prompt(settled))
        elif settled.get("status") == "completed":
            st.success("Run completed.")
        else:
            st.warning(
                f"Run `{new_run_id}` is still in progress (status: {settled.get('status')}). "
                "Use **Refresh status** in the sidebar."
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
        st.warning(
            f"Polling timed out, but run `{new_run_id or 'unknown'}` may still be running in the "
            "background. Click **Refresh status** in the sidebar in a minute or two."
        )
    except httpx.HTTPError as exc:
        st.session_state.messages.append(
            {"role": "assistant", "content": f"Failed to start run: {exc}"},
        )
        st.error(f"Failed to start run: {exc}")
    finally:
        st.session_state.is_processing = False


def load_run_from_history(client: httpx.Client, run_id: str) -> None:
    status = get_run(client, run_id)
    st.session_state.run_id = run_id
    st.session_state.run_status = status
    st.session_state.messages = _rebuild_messages_from_run(status)
