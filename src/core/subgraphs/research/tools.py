from langchain_core.tools import BaseTool, tool


@tool
def search_evidence(research_questions: list[str], todos: list[str]) -> dict:
    """Search external evidence via MCP for fitness research questions."""
    ...


@tool
def retrieve_documents(source_ids: list[str]) -> dict:
    """Retrieve full document content for ranked sources via MCP."""
    ...


@tool
def rank_sources(sources: list[dict]) -> dict:
    """Rank retrieved sources by relevance and evidence quality."""
    ...


@tool
def verify_sources(sources: list[dict]) -> dict:
    """Verify source credibility and fitness-domain relevance."""
    ...


RESEARCH_TOOLS: list[BaseTool] = [
    search_evidence,
    retrieve_documents,
    rank_sources,
    verify_sources,
]
