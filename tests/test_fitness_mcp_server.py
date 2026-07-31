"""In-process tool-level tests for the Fitness MCP Server -- calls the
@mcp.tool()-decorated functions directly via FitnessServerTools, no transport layer.

Requires a real OPENAI_API_KEY (search_guidelines embeds the query for real) and the
real local Postgres instance (pgvector-enabled), with bootstrap_schema() applied.
"""

from __future__ import annotations

import pytest

from core.adapters.db.bootstrap import bootstrap_schema
from core.adapters.db.guideline_repository import GuidelineRepository
from core.adapters.db.template_repository import TemplateRepository
from core.adapters.mcp.fitness_server import build_server
from core.config.settings import get_settings
from core.shared.knowledge.embeddings import get_embedding_provider
from core.shared.knowledge.schema import KnowledgeChunk, KnowledgeDocument, KnowledgeSource

pytestmark = pytest.mark.skipif(
    not get_settings().openai_api_key,
    reason="Requires a real OPENAI_API_KEY (search_guidelines embeds the query for real)",
)


@pytest.fixture
def server_tools():
    settings = get_settings()
    bootstrap_schema(settings.checkpointer_dsn)

    guideline_repo = GuidelineRepository(settings.checkpointer_dsn)
    guideline_repo.reset()
    embeddings = get_embedding_provider(settings)
    content = "Progressive overload increases training volume over time."
    source = KnowledgeSource(id="doc-1", title="Doc 1", trust_score=0.95)
    document = KnowledgeDocument(id="doc-1", source_id="doc-1", title="Doc 1", category="general")
    chunk = KnowledgeChunk(id="doc-1::0", document_id="doc-1", chunk_index=0, content=content)
    vector = embeddings.embed_documents([content])[0]
    guideline_repo.upsert(source, document, [(chunk, vector)])
    guideline_repo.close()

    template_repo = TemplateRepository(settings.checkpointer_dsn)
    template_repo.reset()

    _server, tools = build_server(settings)
    yield tools

    GuidelineRepository(settings.checkpointer_dsn).reset()
    template_repo.reset()
    template_repo.close()


def test_search_guidelines_returns_seeded_document(server_tools) -> None:
    result = server_tools.search_guidelines(query="progressive overload training volume")
    assert result["documents"]
    assert result["documents"][0]["document_id"] == "doc-1"


def test_search_training_template_missing_returns_none(server_tools) -> None:
    assert server_tools.search_training_template("missing-fingerprint") == {"workout": None}


def test_store_then_search_training_template_round_trips(server_tools) -> None:
    workout = {"split": "full body", "weekly_sets": 12}
    assert server_tools.store_training_template("fp-1", workout) == {"stored": True}
    assert server_tools.search_training_template("fp-1") == {"workout": workout}
