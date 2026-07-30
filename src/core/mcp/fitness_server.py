"""Fitness MCP Server -- sole owner of Fitness domain knowledge (guideline documents +
workout templates), backed by PostgreSQL + pgvector.

Runs as its own standalone process: `uv run python -m core.mcp.fitness_server`.
Exposes business-capability tools only (search_guidelines, search_training_template,
store_training_template) -- never SQL, never raw repository methods.

build_server() wires repositories/service via closures over locally-constructed
dependencies -- called once from __main__ (production) or directly by
tests/test_fitness_mcp_server.py with a test DSN. Importing this module alone never
opens a Postgres connection.
"""

from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

from mcp.server.fastmcp import FastMCP

from core.config.settings import Settings, get_settings
from core.repositories.guideline_repository import GuidelineRepository
from core.repositories.template_repository import TemplateRepository
from core.shared.knowledge.embeddings import get_embedding_provider
from core.shared.knowledge.retrieval_service import build_retrieval_service

mcp = FastMCP("fitness-knowledge")


@dataclass(frozen=True)
class FitnessServerTools:
    """Direct references to the tool functions, for test_fitness_mcp_server.py to call
    without going through the MCP transport layer."""

    search_guidelines: Callable[..., dict[str, Any]]
    search_training_template: Callable[[str], dict[str, Any]]
    store_training_template: Callable[[str, dict[str, Any]], dict[str, Any]]


def build_server(settings: Settings) -> tuple[FastMCP, FitnessServerTools]:
    embeddings = get_embedding_provider(settings)
    guideline_repo = GuidelineRepository(settings.checkpointer_dsn)
    template_repo = TemplateRepository(settings.checkpointer_dsn)
    retrieval = build_retrieval_service(guideline_repo, embeddings, settings)

    @mcp.tool()
    def search_guidelines(
        query: str,
        goal: str = "",
        equipment: str = "",
        limit: int = 3,
        min_documents: int = 1,
        min_trust_score: float = 0.85,
    ) -> dict[str, Any]:
        """Ranked guideline documents for a research task, plus whether they're
        sufficient to skip external research."""
        hits = retrieval.search(
            kind="guideline",
            query=query,
            goal=goal,
            equipment=equipment,
            limit=limit,
            min_similarity=settings.fitness_kb_min_similarity,
        )
        sufficient = retrieval.has_sufficient_coverage(
            hits, min_documents=min_documents, min_trust_score=min_trust_score
        )
        return {
            "documents": [hit.model_dump() for hit in hits],
            "sufficient_coverage": sufficient,
        }

    @mcp.tool()
    def search_training_template(fingerprint: str) -> dict[str, Any]:
        """Look up a previously generated structured workout by fingerprint."""
        return {"workout": template_repo.get(fingerprint)}

    @mcp.tool()
    def store_training_template(fingerprint: str, workout: dict[str, Any]) -> dict[str, Any]:
        """Persist an LLM-generated structured workout for cross-run reuse."""
        template_repo.put(fingerprint, workout)
        return {"stored": True}

    return mcp, FitnessServerTools(
        search_guidelines=search_guidelines,
        search_training_template=search_training_template,
        store_training_template=store_training_template,
    )


if __name__ == "__main__":
    _settings = get_settings()
    _server, _tools = build_server(_settings)
    # FastMCP.run() takes no host/port kwargs -- those live on its settings object.
    _server.settings.host = _settings.fitness_mcp_host
    _server.settings.port = _settings.fitness_mcp_port
    _server.run(transport="streamable-http")
