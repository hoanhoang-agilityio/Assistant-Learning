"""The training and nutrition knowledge base: chunking, embedding, retrieval.

Two halves that must agree, which is why they live in one module. The seeder
(``scripts/seed_knowledge.py``) turns ``data/knowledge/*.docx`` into passages and
embeds them; ``search_knowledge`` embeds a question and finds the nearest ones.
Split across two modules, they drift — a different embedding model on each side
produces vectors that compare cleanly and mean nothing.

**A section is a chunk.** The source documents are written one topic per
``Heading 2``, and that heading is the retrieval unit a question actually maps
onto: "how much protein" wants the Protein section, not a 200-character window
that happens to straddle it. Fixed-size splitting is the fallback for a section
too long to embed whole, not the default.

**The heading is embedded with the body.** "Adequate hydration supports health"
is a sentence about water only if you already know which section it came from;
the embedding does not, unless the heading is in the text.

**Retrieval degrades to nothing, never to an error.** Every failure path returns
``[]``, which the QA prompt already handles: answer from your own knowledge and
say the knowledge base had no material on it. A pgvector timeout costs a
citation, not the answer.

Deliberately uncached. A short-lived cache would not pay: questions repeat
across users on a much longer scale than any TTL worth holding, and a stale
passage is worth less than the one embedding call it saves.
"""

import asyncio
import hashlib
import re
from pathlib import Path
from typing import Any

from docx import Document
from langchain_openai import OpenAIEmbeddings
from langchain_text_splitters import RecursiveCharacterTextSplitter
from pydantic import BaseModel
from sqlmodel import Session, select

from app.core.configs.config import settings
from app.core.logging import logger
from app.models.database import engine
from app.models.knowledge import KnowledgeChunk

# A section longer than this is split. Roughly 400 tokens: comfortably inside
# the embedding model's window, and small enough that four retrieved passages
# still leave room for the conversation in the QA prompt.
MAX_CHUNK_CHARS = 1500

# Carried between split parts so a sentence cut in half is retrievable from
# either side.
_CHUNK_OVERLAP_CHARS = 150

# Word-style names for the section boundary. "Title" and "Heading 1" name the
# document; "Heading 2" and deeper start a section.
_TITLE_STYLES = frozenset({"Title", "Heading 1"})
_HEADING_PATTERN = re.compile(r"^Heading (\d+)$")


class Chunk(BaseModel):
    """One passage, ready to embed and store."""

    id: str
    source: str
    heading: str
    chunk_index: int
    text: str
    content_hash: str


class Passage(BaseModel):
    """One retrieved passage, shaped as ``search_knowledge`` returns it."""

    text: str
    source: str
    score: float


def _slug(value: str) -> str:
    """Reduce a title or heading to an id-safe fragment.

    Args:
        value: Human-readable text.

    Returns:
        Lowercase, hyphen-separated, punctuation removed.
    """
    cleaned = re.sub(r"[^a-z0-9]+", "-", value.lower()).strip("-")
    return cleaned or "section"


def _clean_title(value: str) -> str:
    """Tidy a document title for display.

    ``source`` is the citation the user sees, and two of the three shipped
    documents carry their file name as the heading, underscores and all.

    Args:
        value: Raw title text, from the document or its file name.

    Returns:
        The title with underscores turned back into spaces.
    """
    return " ".join(value.replace("_", " ").split())


def content_hash(text: str) -> str:
    """Fingerprint a passage so an unchanged one is not re-embedded.

    Args:
        text: The passage exactly as it will be embedded.

    Returns:
        A hex digest.
    """
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _split_long(body: str) -> list[str]:
    """Split a section that is too long to embed as one passage.

    Args:
        body: The section body.

    Returns:
        One entry when the section fits, several overlapping ones otherwise.
    """
    if len(body) <= MAX_CHUNK_CHARS:
        return [body]

    splitter = RecursiveCharacterTextSplitter(
        chunk_size=MAX_CHUNK_CHARS, chunk_overlap=_CHUNK_OVERLAP_CHARS
    )
    return splitter.split_text(body)


def chunk_document(path: Path) -> list[Chunk]:
    """Turn one ``.docx`` knowledge document into passages.

    Sections are delimited by ``Heading 2`` and deeper; the document title comes
    from ``Title`` or ``Heading 1``, falling back to the file name. A section
    with a heading and no body is dropped — it is a container, and embedding a
    heading on its own produces a passage that matches queries and tells the
    reader nothing.

    Args:
        path: Path to the document.

    Returns:
        Passages in reading order. Ids are deterministic, so re-running this on
        an unchanged document produces exactly the same ids.
    """
    document = Document(str(path))
    title = _clean_title(path.stem)
    doc_slug = _slug(path.stem)

    chunks: list[Chunk] = []
    used_ids: set[str] = set()
    heading = ""
    body: list[str] = []

    def flush() -> None:
        """Emit the accumulated section, if it has both a heading and a body."""
        if not heading or not body:
            return

        joined = "\n\n".join(body)
        for part in _split_long(joined):
            text = f"{heading}\n\n{part}".strip()
            chunk_id = f"{doc_slug}#{_slug(heading)}"
            # Two sections may share a heading, and two split parts always do.
            # A collision would make the seeder's upsert overwrite one passage
            # with the other and quietly lose it.
            suffix = 2
            while chunk_id in used_ids:
                chunk_id = f"{doc_slug}#{_slug(heading)}-{suffix}"
                suffix += 1
            used_ids.add(chunk_id)

            chunks.append(
                Chunk(
                    id=chunk_id,
                    source=title,
                    heading=heading,
                    chunk_index=len(chunks),
                    text=text,
                    content_hash=content_hash(text),
                )
            )

    for paragraph in document.paragraphs:
        text = paragraph.text.strip()
        if not text:
            continue

        style = paragraph.style.name if paragraph.style is not None else ""
        if style in _TITLE_STYLES:
            flush()
            heading, body = "", []
            title = _clean_title(text)
            continue

        match = _HEADING_PATTERN.match(style)
        if match and int(match.group(1)) >= 2:
            flush()
            heading, body = text, []
            continue

        body.append(text)

    flush()

    logger.info("knowledge_document_chunked", source=title, chunks=len(chunks))
    return chunks


def chunk_directory(directory: Path) -> list[Chunk]:
    """Chunk every ``.docx`` document in a directory.

    Args:
        directory: Folder holding the knowledge documents.

    Returns:
        Passages from all documents, ordered by file name so a re-run is stable.
    """
    chunks: list[Chunk] = []
    for path in sorted(directory.glob("*.docx")):
        # Word writes a lock file next to an open document. It is not a document.
        if path.name.startswith("~$"):
            continue
        chunks.extend(chunk_document(path))
    return chunks


class KnowledgeService:
    """Embedding and similarity search over the knowledge base."""

    def __init__(self) -> None:
        """Prepare a lazily-created embeddings client."""
        self._embedder: Any = None
        self._unavailable = False

    @property
    def enabled(self) -> bool:
        """Whether the knowledge base can be queried at all.

        Returns:
            ``False`` when no API key is configured or the embeddings client
            could not be built, so callers can skip the work entirely.
        """
        return not self._unavailable

    def _get_embedder(self) -> Any:
        """Return the embeddings client, creating it on first use.

        Returns:
            The ``OpenAIEmbeddings`` instance, or ``None`` when it cannot be
            built — which includes the case of no API key being configured.
        """
        if self._embedder is not None or self._unavailable:
            return self._embedder

        if not settings.OPENAI_API_KEY:
            self._unavailable = True
            logger.info("knowledge_disabled_no_api_key")
            return None

        try:
            self._embedder = OpenAIEmbeddings(
                model=settings.KNOWLEDGE_EMBEDDER_MODEL,
                api_key=settings.OPENAI_API_KEY,
            )
            logger.info("knowledge_embedder_initialized", model=settings.KNOWLEDGE_EMBEDDER_MODEL)
        except Exception as e:
            self._unavailable = True
            logger.warning("knowledge_embedder_unavailable", error=str(e))

        return self._embedder

    async def embed_texts(self, texts: list[str]) -> list[list[float]]:
        """Embed passages for storage.

        Unlike :meth:`search`, this raises: the seeder must fail loudly rather
        than write a knowledge base with holes in it.

        Args:
            texts: Passage bodies.

        Returns:
            One vector per input, in the same order.

        Raises:
            RuntimeError: If no embeddings client is available.
        """
        if not texts:
            return []

        embedder = self._get_embedder()
        if embedder is None:
            raise RuntimeError(
                "no embeddings client: set OPENAI_API_KEY before seeding the knowledge base"
            )

        return await embedder.aembed_documents(texts)

    async def search(self, query: str, top_k: int | None = None) -> list[Passage]:
        """Find the passages closest to a question.

        Args:
            query: The question, in the user's own words.
            top_k: Maximum passages to return. Defaults to
                ``settings.KNOWLEDGE_TOP_K``.

        Returns:
            Passages above ``settings.KNOWLEDGE_MIN_SCORE``, closest first. Empty
            when nothing clears the floor, the base is unpopulated, or anything
            at all went wrong.
        """
        if not query.strip() or self._unavailable:
            return []

        embedder = self._get_embedder()
        if embedder is None:
            return []

        limit = top_k or settings.KNOWLEDGE_TOP_K

        try:
            vector = await embedder.aembed_query(query)
            # The session API is synchronous; a node awaiting it on the event
            # loop would block every other request for the round trip.
            rows = await asyncio.to_thread(_nearest, vector, limit)
        except Exception as e:
            logger.exception("knowledge_search_failed", error=str(e))
            return []

        passages = [
            Passage(text=chunk.text, source=chunk.source, score=round(score, 4))
            for chunk, score in rows
            if score >= settings.KNOWLEDGE_MIN_SCORE
        ]

        logger.info(
            "knowledge_searched",
            results=len(passages),
            retrieved=len(rows),
            top_score=passages[0].score if passages else 0.0,
        )
        return passages


def _nearest(vector: list[float], limit: int) -> list[tuple[KnowledgeChunk, float]]:
    """Fetch the nearest stored passages to an embedded query.

    Args:
        vector: The embedded query.
        limit: How many rows to retrieve.

    Returns:
        ``(chunk, score)`` pairs, closest first, where score is cosine
        similarity in ``[0, 1]`` — the complement of the distance pgvector's
        ``<=>`` operator returns.
    """
    distance = KnowledgeChunk.embedding.cosine_distance(vector)  # type: ignore[attr-defined]
    statement = select(KnowledgeChunk, distance.label("distance")).order_by(distance).limit(limit)

    with Session(engine) as session:
        return [(chunk, 1.0 - float(value)) for chunk, value in session.exec(statement).all()]


knowledge_service = KnowledgeService()

__all__ = [
    "MAX_CHUNK_CHARS",
    "Chunk",
    "KnowledgeService",
    "Passage",
    "chunk_directory",
    "chunk_document",
    "content_hash",
    "knowledge_service",
]
