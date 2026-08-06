"""Semantic search over the training and nutrition knowledge base."""

from langchain_core.tools import tool

from app.core.logging import logger
from app.services.knowledge import knowledge_service


@tool
async def search_knowledge(query: str, top_k: int = 4) -> list[dict]:
    """Search the training and nutrition knowledge base.

    Only for answering general knowledge questions. Never use it to retrieve
    data for building or assessing a plan — that data comes from the catalog and
    the rubrics, through the graph, not through this tool.

    Args:
        query: Natural-language question to search for.
        top_k: Maximum number of passages to return.

    Returns:
        Passages as ``{"text": str, "source": str, "score": float}``. An empty
        list means nothing relevant was found; answer from your own knowledge and
        say the knowledge base had no material on it, rather than inventing a
        citation.
    """
    passages = await knowledge_service.search(query, top_k=top_k)
    logger.info("search_knowledge_called", query=query, top_k=top_k, results=len(passages))
    return [passage.model_dump() for passage in passages]
