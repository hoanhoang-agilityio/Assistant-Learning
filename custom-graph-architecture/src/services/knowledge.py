"""The knowledge base's embedding pipeline: Word documents in, storable rows out."""

import hashlib
import re
from functools import lru_cache
from pathlib import Path
from typing import Any

from docx import Document
from langchain_openai import OpenAIEmbeddings
from langchain_text_splitters import RecursiveCharacterTextSplitter
from pydantic import BaseModel
from sqlmodel import select

from src.core.configs.config import settings
from src.models.knowledge import KnowledgeChunk
from src.schemas import RetrievedChunk
from src.services.database import session_factory
from src.utils.logging import logger

KNOWLEDGE_DIR = Path("data/knowledge")

MAX_CHUNK_CHARS = 1500
CHUNK_OVERLAP_CHARS = 150

CANDIDATE_MULTIPLIER = 3

SHINGLE_WORDS = 2

# Word's own names for the paragraph styles. "Title" and "Heading 1" name the document;
# "Heading 2" and deeper start a section.
TITLE_STYLES = frozenset({"Title", "Heading 1"})
SECTION_LEVEL = 2

_HEADING_STYLE = re.compile(r"^Heading (\d+)$")
_NON_SLUG = re.compile(r"[^a-z0-9]+")
_WORD = re.compile(r"[a-z0-9]+")


class Chunk(BaseModel):
    """One passage of a knowledge document, ready to embed."""

    id: str
    source: str
    heading: str
    chunk_index: int
    text: str
    content_hash: str


def content_hash(text: str) -> str:
    """Fingerprint a passage so an unchanged one need not be embedded again."""

    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _slug(value: str) -> str:
    """Reduce a title or heading to an id-safe fragment."""

    return _NON_SLUG.sub("-", value.lower()).strip("-") or "section"


def _title(value: str) -> str:
    """Tidy a document title into the citation the user sees. """

    return " ".join(value.replace("_", " ").split())


def _unique_id(base: str, used: set[str]) -> str:
    """A collision-free chunk id, so two same-named sections cannot overwrite each other."""

    candidate, suffix = base, 2
    while candidate in used:
        candidate, suffix = f"{base}-{suffix}", suffix + 1

    used.add(candidate)
    return candidate


def _split_long(body: str) -> list[str]:
    """Split a section only when it is too long to embed as one passage."""

    if len(body) <= MAX_CHUNK_CHARS:
        return [body]

    splitter = RecursiveCharacterTextSplitter(
        chunk_size=MAX_CHUNK_CHARS, chunk_overlap=CHUNK_OVERLAP_CHARS
    )
    return splitter.split_text(body)


def read_sections(path: Path) -> tuple[str, list[tuple[str, str]]]:
    """A document's title and its ``Heading 2``-and-deeper sections, in reading order."""

    title = ""
    heading = ""
    body: list[str] = []
    sections: list[tuple[str, str]] = []

    def flush() -> None:
        joined = "\n\n".join(body).strip()
        if heading and joined:
            sections.append((heading, joined))

    for paragraph in Document(str(path)).paragraphs:
        text = paragraph.text.strip()
        if not text:
            continue

        style = paragraph.style.name if paragraph.style is not None else ""
        if style in TITLE_STYLES:
            flush()
            title, heading, body = title or text, "", []
            continue

        match = _HEADING_STYLE.match(style)
        if match and int(match.group(1)) >= SECTION_LEVEL:
            flush()
            heading, body = text, []
            continue

        body.append(text)

    flush()
    return title, sections


def chunk_document(path: Path) -> list[Chunk]:
    """Turn one Word knowledge document into passages with stable ids."""

    title, sections = read_sections(path)
    source = _title(title or path.stem)
    document = _slug(path.stem)

    chunks: list[Chunk] = []
    used: set[str] = set()

    for heading, body in sections:
        for part in _split_long(body):
            text = f"{heading}\n\n{part}"
            chunks.append(
                Chunk(
                    id=_unique_id(f"{document}#{_slug(heading)}", used),
                    source=source,
                    heading=heading,
                    chunk_index=len(chunks),
                    text=text,
                    content_hash=content_hash(text),
                )
            )

    return chunks


def chunk_directory(directory: Path = KNOWLEDGE_DIR) -> list[Chunk]:
    """Chunk every Word document in a directory, ordered so a re-run is stable."""

    chunks: list[Chunk] = []
    for path in sorted(directory.glob("*.docx")):
        # Word writes a lock file beside an open document. It is not a document.
        if path.name.startswith("~$"):
            continue
        chunks.extend(chunk_document(path))

    return chunks


@lru_cache
def embedder() -> OpenAIEmbeddings:
    """The embedding client, shared by the seeder and by retrieval."""

    return OpenAIEmbeddings(
        model=settings.KNOWLEDGE_EMBEDDER_MODEL,
        api_key=settings.OPENAI_API_KEY,
        dimensions=settings.KNOWLEDGE_EMBEDDING_DIM,
    )


async def embed_chunks(chunks: list[Chunk]) -> list[dict[str, Any]]:
    """Embed the passages and return them shaped as ``knowledge_chunks`` rows."""

    if not chunks:
        return []

    vectors = await embedder().aembed_documents([chunk.text for chunk in chunks])

    return [
        chunk.model_dump() | {"embedding": vector}
        for chunk, vector in zip(chunks, vectors, strict=True)
    ]


async def _nearest(
    vector: list[float], limit: int
) -> list[tuple[KnowledgeChunk, float]]:
    """The stored passages nearest an embedded question, closest first, scored by cosine similarity."""

    distance = KnowledgeChunk.embedding.cosine_distance(vector)
    statement = (
        select(KnowledgeChunk, distance.label("distance"))
        .order_by(distance)
        .limit(limit)
    )

    async with session_factory() as session:
        rows = (await session.execute(statement)).all()

    return [(chunk, 1.0 - float(value)) for chunk, value in rows]


def _shingles(text: str) -> frozenset[str]:
    """The adjacent word pairs a passage is compared on, case and punctuation dropped."""

    words = _WORD.findall(text.lower())
    if len(words) < SHINGLE_WORDS:
        return frozenset(words)

    return frozenset(
        f"{first} {second}" for first, second in zip(words, words[1:], strict=False)
    )


def overlap(first: str, second: str) -> float:
    """How much of the shorter passage the longer one already says, in ``[0, 1]``."""

    left, right = _shingles(first), _shingles(second)
    if not left or not right:
        return 0.0

    return len(left & right) / min(len(left), len(right))


def deduplicate(passages: list[RetrievedChunk]) -> list[RetrievedChunk]:
    """Drop a passage that repeats one already kept, keeping the closer of the two."""

    kept: list[RetrievedChunk] = []

    for passage in passages:
        if not any(
            overlap(passage["text"], other["text"]
                    ) >= settings.KNOWLEDGE_MAX_OVERLAP
            for other in kept
        ):
            kept.append(passage)

    return kept


async def search(query: str, top_k: int | None = None) -> list[RetrievedChunk]:
    """The passages that answer a question, closest first, or none good enough to answer from."""

    if not query.strip():
        return []

    limit = top_k or settings.KNOWLEDGE_TOP_K

    try:
        vector = await embedder().aembed_query(query)
        rows = await _nearest(vector, limit * CANDIDATE_MULTIPLIER)
    except Exception as error:
        logger.exception("knowledge_search_failed", error=str(error))
        return []

    relevant = [
        RetrievedChunk(text=chunk.text, source=chunk.source,
                       score=round(score, 4))
        for chunk, score in rows
        if score >= settings.KNOWLEDGE_MIN_SCORE
    ]

    return deduplicate(relevant)[:limit]
