"""Friendly copy for pipeline steps, run status, and HITL states.

Maps internal LangGraph node/step identifiers (e.g. "research:research_agent",
step ids are always "{subgraph}:{node}" per core/subgraphs/wrapper.py, or a
bare top-level node name like "hitl") to short, human-friendly progress
messages with an icon and a phase color — so the UI never surfaces raw
backend node names to the user.
"""

from __future__ import annotations

PHASE_COLORS: dict[str, str] = {
    "supervisor": "#64748B",
    "planning": "#8B5CF6",
    "research": "#3B82F6",
    "fitness": "#F97316",
    "verification": "#14B8A6",
    "hitl": "#EC4899",
    "persist": "#4CAF50",
}

PHASE_ICONS: dict[str, str] = {
    "supervisor": "🧭",
    "planning": "🗺️",
    "research": "🔎",
    "fitness": "🏋️",
    "verification": "🔍",
    "hitl": "🙋",
    "persist": "💾",
}

PHASE_LABELS: dict[str, str] = {
    "supervisor": "Coordinating",
    "planning": "Planning",
    "research": "Researching",
    "fitness": "Building your plan",
    "verification": "Reviewing",
    "hitl": "Needs you",
    "persist": "Saving",
}

# step id ("subgraph:node" or a bare top-level node name) -> (icon, message)
STEP_COPY: dict[str, tuple[str, str]] = {
    "supervisor": ("🧭", "Deciding the best next step…"),
    "supervisor:route": ("🧭", "Deciding the best next step…"),
    "planning": ("🗺️", "Working on your plan…"),
    "planning:extract_profile": ("📝", "Understanding your goals and profile…"),
    "planning:validate_profile": ("✅", "Checking your profile is complete…"),
    "planning:generate_plan": ("🗺️", "Drafting your training roadmap…"),
    "planning:reuse_execution_plan": ("♻️", "Reusing your existing plan outline…"),
    "planning:planning_hitl": ("❓", "Need a bit more info from you…"),
    "research": ("🔎", "Researching…"),
    "research:todos_gate": ("📋", "Preparing research inputs…"),
    "research:research_agent": ("🔎", "Researching evidence-based training methods…"),
    "research:write_artifacts": ("💾", "Saving research findings…"),
    "research:blocked": ("⏸️", "Waiting on plan details before researching…"),
    "fitness": ("🏋️", "Building your plan…"),
    "fitness:load_context": ("📥", "Gathering everything needed to build your plan…"),
    "fitness:build_blueprint": ("📐", "Sketching your program structure…"),
    "fitness:calculate_macros": ("🧮", "Calculating your calorie and macro targets…"),
    "fitness:resolve_workout_template": ("🔁", "Checking for a matching workout template…"),
    "fitness:fitness_planner": ("🏋️", "Designing your workout plan…"),
    "fitness:fitness_planner_retry": ("🛠️", "Refining your workout for safety…"),
    "fitness:reuse_workout_template": ("♻️", "Adapting a proven workout template…"),
    "fitness:safety_check": ("🛡️", "Running safety checks on your plan…"),
    "fitness:synthesize_plan": ("📄", "Putting together your draft plan…"),
    "fitness:write_artifacts": ("💾", "Saving your draft plan…"),
    "verification": ("🔍", "Reviewing your plan…"),
    "verification:load_context": ("📥", "Loading your plan for review…"),
    "verification:citation_check": ("📚", "Verifying claims are backed by evidence…"),
    "verification:consistency_check": ("🔍", "Double-checking plan consistency…"),
    "verification:safety_check": ("🛡️", "Confirming your plan is safe…"),
    "verification:ragas_faithfulness": ("📊", "Scoring how well the plan matches the research…"),
    "verification:write_artifacts": ("💾", "Saving verification results…"),
    "hitl": ("🙋", "Waiting for your input…"),
    "persist": ("💾", "Saving your final plan…"),
    "persist:persist_trigger_blocked": ("⏸️", "Finishing up…"),
    "persist:save_run": ("💾", "Saving your final plan…"),
    "persist:save_metrics": ("📊", "Recording plan metrics…"),
    "persist:save_artifacts": ("💾", "Saving your final plan…"),
}

STATUS_COPY: dict[str, tuple[str, str]] = {
    "running": ("⏳", "Working on it…"),
    "waiting_hitl": ("🙋", "Waiting for your response…"),
    "completed": ("✅", "Done!"),
    "failed": ("⚠️", "Something went wrong."),
    "refused": ("🚫", "That's outside what I can help with."),
}

HITL_TYPE_COPY: dict[str, str] = {
    "clarification": "Just need a couple more details from you.",
    "approval": "Your plan is ready — take a look.",
    "tool_approval": "Approve this action to continue.",
    "profile_form": "Let's fill in a few details to build your plan.",
}

# goal-feasibility issue code (core/profile/goal_spec.py's assess_goal_feasibility) -> friendly
# message. Mirrors that module's own _feasibility_message wording so the profile form banner
# and the backend's internal reasoning stay in sync without importing across the API boundary.
FEASIBILITY_ISSUE_COPY: dict[str, str] = {
    "unrealistic_fat_loss_rate": (
        "This target would require an unsafe rate of weight loss. "
        "Consider a lower target rate or a longer timeline."
    ),
    "aggressive_fat_loss_rate": (
        "This is an aggressive fat-loss rate. You can continue, but consider a longer timeline."
    ),
    "aggressive_muscle_gain_rate": (
        "This is an aggressive muscle-gain rate. You can continue, but consider a longer timeline."
    ),
    "goal_direction_conflict:fat_loss_positive_delta": (
        "Your goal is fat loss, but the target weight is higher than your current weight. "
        "Please double-check your numbers."
    ),
    "goal_direction_conflict:muscle_gain_negative_delta": (
        "Your goal is muscle gain, but the target weight is lower than your current weight. "
        "Please double-check your numbers."
    ),
}


def feasibility_messages(issues: list[str]) -> list[str]:
    """Map feasibility issue codes to friendly messages, deduped and in original order."""
    seen: set[str] = set()
    messages: list[str] = []
    for issue in issues:
        message = FEASIBILITY_ISSUE_COPY.get(issue)
        if message and message not in seen:
            seen.add(message)
            messages.append(message)
    return messages


APPROVAL_STATUS_COPY: dict[str, str] = {
    "approved": "Approved — saving now…",
    "rejected": "Plan rejected. Nothing was saved.",
    "revision_requested": "Got it — reworking your plan…",
}

ROUTE_DECISION_COPY: dict[str, str] = {
    "REPLAN": "Refining the plan based on your feedback…",
    "RERESEARCH": "Digging up more research to fix an issue…",
    "FIX_REASONING": "Fixing an issue with the workout plan…",
    "HITL": "Pausing to check in with you…",
    "COMPLETE": "Wrapping things up…",
}


def phase_of(step_id: str) -> str:
    """Return the phase/subgraph a step id belongs to.

    e.g. "research:research_agent" -> "research"; "hitl" -> "hitl".
    """
    return step_id.split(":", 1)[0]


def _prettify(step_id: str) -> str:
    name = step_id.split(":", 1)[-1].replace("_", " ").strip()
    return f"{name.capitalize()}…"


def step_display(step_id: str) -> tuple[str, str]:
    """Return (icon, friendly message) for a step id, falling back to a prettified name."""
    if step_id in STEP_COPY:
        return STEP_COPY[step_id]
    phase = phase_of(step_id)
    return PHASE_ICONS.get(phase, "⚙️"), _prettify(step_id)


def phase_color(step_id: str) -> str:
    return PHASE_COLORS.get(phase_of(step_id), "#64748B")


def phase_label(step_id: str) -> str:
    return PHASE_LABELS.get(phase_of(step_id), "Working")


def status_display(status: str) -> tuple[str, str]:
    return STATUS_COPY.get(status, ("⏳", "Working on it…"))
