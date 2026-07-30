"""Raw record loaders for the knowledge ingestion pipeline.

Loader is the extension point for future formats (PDF, Markdown, PubMed exports) --
each implementation feeds the same downstream Validator/Chunker/Repository pipeline.
"""

import json
from collections.abc import Iterator
from pathlib import Path
from typing import Any, Protocol

RawKnowledgeRecord = dict[str, Any]


class Loader(Protocol):
    def load(self) -> Iterator[RawKnowledgeRecord]: ...


class JSONLLoader:
    """Loads today's flat corpus.jsonl rows: one JSON object per line."""

    def __init__(self, path: Path) -> None:
        self._path = path

    def load(self) -> Iterator[RawKnowledgeRecord]:
        if not self._path.exists():
            return
        for line in self._path.read_text(encoding="utf-8").splitlines():
            stripped = line.strip()
            if not stripped:
                continue
            yield json.loads(stripped)
