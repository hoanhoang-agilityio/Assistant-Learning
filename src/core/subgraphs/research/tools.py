from langchain_core.tools import BaseTool, tool

from core.subgraphs.research.utils import (
    rank_sources_data,
    retrieve_documents_data,
    search_evidence_data,
    verify_sources_data,
)


@tool
def search_evidence(research_questions: list[str], todos: list[str]) -> dict:
    """Search external evidence via Tavily MCP for fitness research questions."""
    return search_evidence_data(research_questions, todos)


@tool
def retrieve_documents(source_ids: list[str], sources: list[dict]) -> dict:
    """Retrieve full document content for ranked sources via Tavily MCP."""
    return retrieve_documents_data(source_ids, sources)


@tool
def rank_sources(sources: list[dict]) -> dict:
    """Rank retrieved sources by relevance and evidence quality."""
    return rank_sources_data(sources)


@tool
def verify_sources(sources: list[dict]) -> dict:
    """Verify source credibility and fitness-domain relevance."""
    return verify_sources_data(sources)


RESEARCH_TOOLS: list[BaseTool] = [
    search_evidence,
    retrieve_documents,
    rank_sources,
    verify_sources,
]
