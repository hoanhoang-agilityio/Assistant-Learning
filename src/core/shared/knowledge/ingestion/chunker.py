"""Splits document content into embeddable chunks.

Wraps langchain_text_splitters.RecursiveCharacterTextSplitter rather than hand-rolling
paragraph-boundary splitting -- already a dependency, purpose-built for this.
"""

from typing import Protocol

from langchain_text_splitters import RecursiveCharacterTextSplitter

from core.shared.knowledge.schema import KnowledgeChunk


class Chunker(Protocol):
    def chunk(self, document_id: str, content: str) -> list[KnowledgeChunk]: ...


class SimpleChunker:
    """Content under `max_chars` stays a single chunk (today's seed docs, all well
    under the default 2000-char threshold, each produce exactly one). Longer content
    splits via RecursiveCharacterTextSplitter's paragraph/sentence/word fallback
    boundaries with the given overlap."""

    def __init__(self, max_chars: int = 2000, chunk_overlap: int = 200) -> None:
        self._splitter = RecursiveCharacterTextSplitter(
            chunk_size=max_chars, chunk_overlap=chunk_overlap
        )

    def chunk(self, document_id: str, content: str) -> list[KnowledgeChunk]:
        return [
            KnowledgeChunk(
                id=f"{document_id}::{index}",
                document_id=document_id,
                chunk_index=index,
                content=text,
            )
            for index, text in enumerate(self._splitter.split_text(content))
        ]
