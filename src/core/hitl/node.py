import json
from pathlib import Path

from core.agents.state import OrchestrationState
from core.hitl.tools import request_approval, request_clarification
from core.hitl.utils import hitl_control_data
from core.vfs import VFS


def invoke_hitl_node(state: OrchestrationState) -> dict:
    """Process HITL interrupt/resume for clarification or final approval."""
    control = hitl_control_data(
        waiting_for_user=state["waiting_for_user"],
        approval_status=state["approval_status"],
        user_response=state["user_response"],
    )
    updates: dict = {"current_node": "hitl", **control}

    if control.get("waiting_for_user") is False:
        return updates

    if state["route_decision"] == "COMPLETE" or state["verification_passed"]:
        vfs = VFS.for_run(Path(state["workspace_path"]))
        draft_plan = ""
        verification_report: dict = {"passed": state["verification_passed"]}
        if vfs.exists("fitness/final_plan.md"):
            draft_plan = vfs.read("fitness/final_plan.md")
        if vfs.exists("verify/verification_v1.json"):
            verification_report = json.loads(vfs.read("verify/verification_v1.json"))
        approval = request_approval.invoke(
            {
                "draft_plan": draft_plan,
                "verification_report": verification_report,
            }
        )
        updates.update(approval)
        return updates

    missing_fields = state.get("user_profile", {}).get("missing_fields", [])
    if missing_fields:
        clarification = request_clarification.invoke(
            {
                "missing_fields": missing_fields,
                "context": state["query"],
            }
        )
        updates.update(clarification)
        return updates

    updates["approval_status"] = state["approval_status"] or "pending"
    updates["waiting_for_user"] = True
    return updates
