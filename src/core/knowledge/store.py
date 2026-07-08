"""File-backed storage for the local fitness knowledge base."""

import json
from pathlib import Path

from core.config.settings import get_settings
from core.knowledge.schema import KnowledgeDocument

_DEFAULT_CORPUS = Path(__file__).resolve().parent / "data" / "corpus.jsonl"


class KnowledgeStore:
    """Load and query curated local knowledge documents."""

    def __init__(self, corpus_path: Path | None = None) -> None:
        settings = get_settings()
        configured = Path(settings.local_kb_path) if settings.local_kb_path else _DEFAULT_CORPUS
        self._corpus_path = corpus_path or configured
        self._documents: list[KnowledgeDocument] | None = None

    def load_documents(self) -> list[KnowledgeDocument]:
        if self._documents is not None:
            return self._documents
        if not self._corpus_path.exists():
            self._documents = []
            return self._documents
        documents: list[KnowledgeDocument] = []
        for line in self._corpus_path.read_text(encoding="utf-8").splitlines():
            stripped = line.strip()
            if not stripped:
                continue
            documents.append(KnowledgeDocument.model_validate(json.loads(stripped)))
        self._documents = documents
        return documents

    def save_documents(self, documents: list[KnowledgeDocument]) -> None:
        self._corpus_path.parent.mkdir(parents=True, exist_ok=True)
        lines = [doc.model_dump_json() for doc in documents]
        self._corpus_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
        self._documents = documents
