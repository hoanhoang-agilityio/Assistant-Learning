"""Loader/validator/chunker/pipeline unit tests -- no Postgres, no OpenAI needed."""

import json

from langchain_core.embeddings import Embeddings

from core.knowledge.ingestion.chunker import SimpleChunker
from core.knowledge.ingestion.loader import JSONLLoader
from core.knowledge.ingestion.pipeline import run_ingestion_pipeline
from core.knowledge.ingestion.validator import validate_record
from core.knowledge.schema import KnowledgeChunk, KnowledgeDocument, KnowledgeSource


def _write_corpus(tmp_path, records: list[dict]) -> None:
    path = tmp_path / "corpus.jsonl"
    path.write_text("\n".join(json.dumps(record) for record in records) + "\n", encoding="utf-8")


def test_jsonl_loader_yields_one_record_per_line(tmp_path) -> None:
    _write_corpus(
        tmp_path,
        [
            {"id": "a", "title": "A", "content": "content a", "category": "x"},
            {"id": "b", "title": "B", "content": "content b", "category": "x"},
        ],
    )
    records = list(JSONLLoader(tmp_path / "corpus.jsonl").load())
    assert [record["id"] for record in records] == ["a", "b"]


def test_jsonl_loader_skips_blank_lines(tmp_path) -> None:
    path = tmp_path / "corpus.jsonl"
    path.write_text('\n{"id": "a", "title": "A", "content": "c", "category": "x"}\n\n', "utf-8")
    records = list(JSONLLoader(path).load())
    assert len(records) == 1


def test_jsonl_loader_missing_file_yields_nothing(tmp_path) -> None:
    assert list(JSONLLoader(tmp_path / "missing.jsonl").load()) == []


def test_validate_record_splits_flat_record_into_source_and_document() -> None:
    record = {
        "id": "hypertrophy-volume-guideline",
        "title": "Hypertrophy Weekly Set Volume",
        "content": "Most muscle groups respond well to roughly 10-20 hard sets per week.",
        "category": "hypertrophy",
        "tags": ["volume"],
        "goal_applicability": ["muscle_gain"],
        "equipment_applicability": ["gym"],
        "source_type": "guideline",
        "source_url": "local-kb://hypertrophy-volume-guideline",
        "trust_score": 0.95,
    }
    source, document, content = validate_record(record)
    assert isinstance(source, KnowledgeSource)
    assert isinstance(document, KnowledgeDocument)
    assert source.id == document.id == "hypertrophy-volume-guideline"
    assert source.url == "local-kb://hypertrophy-volume-guideline"
    assert source.trust_score == 0.95
    assert document.category == "hypertrophy"
    assert document.kind == "guideline"
    assert content == record["content"]


def test_simple_chunker_short_content_produces_one_chunk() -> None:
    chunker = SimpleChunker(max_chars=2000, chunk_overlap=200)
    chunks = chunker.chunk("doc-1", "A short guideline document under the chunk threshold.")
    assert len(chunks) == 1
    assert chunks[0].id == "doc-1::0"
    assert chunks[0].chunk_index == 0


def test_simple_chunker_long_content_produces_multiple_chunks() -> None:
    """Synthetic long-document case -- real seed data never exercises this path."""
    chunker = SimpleChunker(max_chars=100, chunk_overlap=20)
    long_content = " ".join(f"Sentence number {i} about training volume." for i in range(50))
    chunks = chunker.chunk("doc-long", long_content)
    assert len(chunks) > 1
    assert [chunk.chunk_index for chunk in chunks] == list(range(len(chunks)))
    assert all(chunk.document_id == "doc-long" for chunk in chunks)


class _FakeEmbeddings(Embeddings):
    def embed_documents(self, texts: list[str]) -> list[list[float]]:
        return [[float(len(text))] for text in texts]

    def embed_query(self, text: str) -> list[float]:
        return [float(len(text))]


class _FakeGuidelineRepository:
    def __init__(self) -> None:
        self.upserted: list[tuple] = []

    def upsert(self, source, document, chunks_with_vectors) -> None:
        self.upserted.append((source, document, chunks_with_vectors))


def test_run_ingestion_pipeline_upserts_each_record_with_embedded_chunks(tmp_path) -> None:
    _write_corpus(
        tmp_path,
        [
            {"id": "a", "title": "A", "content": "content a", "category": "x"},
            {"id": "b", "title": "B", "content": "content b", "category": "x"},
        ],
    )
    repository = _FakeGuidelineRepository()
    stats = run_ingestion_pipeline(
        loader=JSONLLoader(tmp_path / "corpus.jsonl"),
        chunker=SimpleChunker(max_chars=2000, chunk_overlap=200),
        embeddings=_FakeEmbeddings(),
        repository=repository,
    )
    assert stats.sources == 2
    assert stats.documents == 2
    assert stats.chunks == 2
    assert len(repository.upserted) == 2
    _source, _document, chunks_with_vectors = repository.upserted[0]
    assert len(chunks_with_vectors) == 1
    chunk, vector = chunks_with_vectors[0]
    assert isinstance(chunk, KnowledgeChunk)
    assert vector == [float(len("content a"))]
