"""The evaluator lists ``run.py`` passes to the batch runner.

Two lists rather than one, because the two scopes see different data: domain
judges read a whole turn's transcript, RAG metrics read a single retrieval and
its passages. Explicit lists — not the template's prompt-directory
auto-discovery — are what make that split expressible.

Importing this module imports ragas, which is the optional ``evals`` extra:

    uv sync --extra evals
"""

from evals.evaluators.domain import DOMAIN_EVALUATORS
from evals.evaluators.rag import RAG_EVALUATORS

__all__ = ["DOMAIN_EVALUATORS", "RAG_EVALUATORS"]
