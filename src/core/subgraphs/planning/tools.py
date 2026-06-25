from langchain_core.tools import BaseTool, tool


@tool
def extract_profile(query: str, user_profile: dict, constraints: dict) -> dict:
    """Extract fitness profile fields from user query and profile data."""
    ...


@tool
def validate_profile(profile: dict) -> dict:
    """Validate profile completeness and flag missing or conflicting fields."""
    ...


@tool
def write_todos(profile: dict, request_type: str | None) -> dict:
    """Write planning todos before research retrieval."""
    ...


PLANNING_TOOLS: list[BaseTool] = [
    extract_profile,
    validate_profile,
    write_todos,
]
