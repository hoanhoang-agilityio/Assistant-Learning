from langchain_core.tools import BaseTool, tool

from core.profile.goal_spec import derive_goal_spec_fields
from core.subgraphs.planning.planning_agent import (
    generate_execution_plan,
    is_planning_agent_overridden,
)
from core.subgraphs.planning.templates import build_template_execution_plan
from core.subgraphs.planning.utils import (
    build_profile,
    persist_execution_plan,
    validate_profile_data,
)


@tool
def extract_profile(
    query: str,
    user_profile: dict,
    constraints: dict,
    revision_feedback: str | None = None,
) -> dict:
    """Extract fitness profile fields from user query and profile data."""
    profile = build_profile(
        query,
        user_profile,
        constraints,
        revision_feedback=revision_feedback,
    )
    return {"profile": profile}


@tool
def validate_profile(profile: dict) -> dict:
    """Validate profile completeness and flag missing or conflicting fields."""
    return validate_profile_data(profile)


@tool
def generate_plan(
    profile: dict,
    query: str,
    request_type: str | None,
    workspace_path: str,
    constraints: dict | None = None,
    revision_feedback: str | None = None,
) -> dict:
    """Generate a structured execution plan via template or Planning Agent."""
    enriched_profile = {**profile, **derive_goal_spec_fields(profile)}
    template_plan = build_template_execution_plan(enriched_profile)
    if (
        template_plan is not None
        and enriched_profile.get("feasibility_level") != "unsafe"
        and not is_planning_agent_overridden()
        and not (revision_feedback or "").strip()
    ):
        return persist_execution_plan(enriched_profile, template_plan, workspace_path)
    plan = generate_execution_plan(
        profile=enriched_profile,
        query=query,
        request_type=request_type,
        constraints=constraints or {},
        revision_feedback=revision_feedback,
    )
    return persist_execution_plan(enriched_profile, plan, workspace_path)


PLANNING_TOOLS: list[BaseTool] = [
    extract_profile,
    validate_profile,
    generate_plan,
]
