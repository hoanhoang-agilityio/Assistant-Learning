from langchain_core.tools import BaseTool, tool

from core.subgraphs.planning.utils import (
    build_profile,
    validate_profile_data,
    write_planning_todos,
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
def write_todos(profile: dict, request_type: str | None, workspace_path: str) -> dict:
    """Write planning todos before research retrieval."""
    return write_planning_todos(profile, request_type, workspace_path)


PLANNING_TOOLS: list[BaseTool] = [
    extract_profile,
    validate_profile,
    write_todos,
]
