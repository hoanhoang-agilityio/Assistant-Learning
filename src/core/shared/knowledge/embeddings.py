"""Embedding provider for the Fitness Knowledge Store.

Reuses langchain_core.embeddings.Embeddings -- the interface this repo already depends
on and already uses for this purpose (core.evaluation.ragas._default_embeddings()) --
rather than inventing a parallel provider abstraction. Swapping to Voyage/Gemini/a
local model later is a change to this one function only: every caller (HybridRetriever,
the ingestion pipeline) depends on Embeddings, never on OpenAI specifically.
"""

from langchain_core.embeddings import Embeddings
from langchain_openai import OpenAIEmbeddings

from core.config.settings import Settings, get_settings


def get_embedding_provider(settings: Settings | None = None) -> Embeddings:
    resolved = settings or get_settings()
    return OpenAIEmbeddings(
        model=resolved.fitness_kb_embedding_model, api_key=resolved.openai_api_key
    )
