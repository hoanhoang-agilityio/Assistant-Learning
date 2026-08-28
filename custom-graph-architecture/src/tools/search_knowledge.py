"""``search_knowledge``: the knowledge base passages that carry the answer to a question."""

import json

from langchain.tools import tool

from src.schemas import RetrievedChunk
from src.services.knowledge import search

NO_PASSAGES = (
    "the knowledge base carries nothing on this question; tell the user there is no trusted"
    " information on it rather than answering from your own knowledge"
)


@tool(response_format="content_and_artifact")
async def search_knowledge(query: str) -> tuple[str, list[RetrievedChunk]]:
    """Search the nutrition, training and injury knowledge base for the passages that answer a question. """

    passages = await search(query)
    if not passages:
        return NO_PASSAGES, []

    return json.dumps(passages, ensure_ascii=False), passages
