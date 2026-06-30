from langchain_core.tools import BaseTool, tool

from core.subgraphs.planning.planning_agent import generate_execution_plan
from core.subgraphs.planning.utils import (
    build_profile,
    persist_execution_plan,
    validate_profile_data,
)


@tool
def extract_profile(query: str, user_profile: dict, constraints: dict) -> dict:
    """Extract fitness profile fields from user query and profile data."""
    profile = build_profile(query, user_profile, constraints)
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
    constraints: dict,
    workspace_path: str,
) -> dict:
    """Generate a structured execution plan via the Planning Agent."""
    plan = generate_execution_plan(
        profile=profile,
        query=query,
        request_type=request_type,
        constraints=constraints,
    )
    return persist_execution_plan(profile, plan, workspace_path)


PLANNING_TOOLS: list[BaseTool] = [
    extract_profile,
    validate_profile,
    generate_plan,
]
