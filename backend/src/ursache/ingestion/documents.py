"""Turn kb.documents rows into kb.chunks rows. Writes kb only; runs as ursache_app."""

from __future__ import annotations

import hashlib
import logging
import uuid
from dataclasses import dataclass
from datetime import date
from pathlib import Path
from typing import Any

import psycopg
from psycopg.rows import class_row
from psycopg.types.json import Jsonb

from ursache.ingestion.chunking import Chunk, chunk_document

logger = logging.getLogger(__name__)

_INSERT = (
    "INSERT INTO kb.chunks (id, document_id, ordinal, text, context_header, section_path,"
    " page, language, token_count, sha256, metadata)"
    " VALUES (%s, %s, %s, %s, %s, %s, NULL, %s, %s, %s, %s)"
)


class IngestionError(RuntimeError):
    pass


@dataclass(frozen=True, slots=True)
class DocumentInfo:
    id: uuid.UUID
    doc_type: str
    title: str
    language: str
    version: str
    effective_from: date
    effective_to: date | None
    source_path: str
    sha256: str


@dataclass(frozen=True, slots=True)
class ChunkRow:
    id: uuid.UUID
    document_id: uuid.UUID
    ordinal: int
    text: str
    context_header: str
    section_path: str
    language: str
    token_count: int
    sha256: str
    metadata: dict[str, Any]


@dataclass(frozen=True, slots=True)
class IngestSummary:
    documents: int
    ingested: int
    skipped: int
    missing: int
    chunks: int


def build_chunk_rows(doc: DocumentInfo, text: str) -> list[ChunkRow]:
    chunks = chunk_document(text, title=doc.title, version=doc.version, source_path=doc.source_path)
    return [_row(doc, c) for c in chunks]


def _row(doc: DocumentInfo, chunk: Chunk) -> ChunkRow:
    return ChunkRow(
        id=uuid.uuid5(doc.id, f"{chunk.ordinal}:{chunk.sha256}"),
        document_id=doc.id,
        ordinal=chunk.ordinal,
        text=chunk.text,
        context_header=chunk.context_header,
        section_path=chunk.section_path,
        language=doc.language,
        token_count=chunk.token_count,
        sha256=chunk.sha256,
        metadata={
            "doc_type": doc.doc_type,
            "version": doc.version,
            "effective_from": doc.effective_from.isoformat(),
            "effective_to": doc.effective_to.isoformat() if doc.effective_to else None,
        },
    )


def ingest_documents(database_url: str, docs_dir: Path, *, force: bool = False) -> IngestSummary:
    """Chunk every kb.documents row whose chunks are missing or out of date.

    Each document's chunks are replaced in their own transaction, so an interrupted run
    leaves every document either fully old or fully new.
    """
    if not docs_dir.is_dir():
        raise IngestionError(f"documents directory not found: {docs_dir}")
    root = docs_dir.resolve()
    ingested = skipped = missing = written = 0
    with psycopg.connect(database_url) as conn:
        with conn.cursor(row_factory=class_row(DocumentInfo)) as cur:
            documents = cur.execute(
                "SELECT id, doc_type, title, language, version, effective_from, effective_to,"
                " source_path, sha256 FROM kb.documents ORDER BY source_path, id"
            ).fetchall()
        stored = {} if force else _stored_chunks(conn)
        conn.commit()
        for doc in documents:
            path = (root / doc.source_path).resolve()
            if not path.is_relative_to(root) or not path.is_file():
                logger.warning(
                    "document file missing; skipped",
                    extra={"document_id": str(doc.id), "source_path": doc.source_path},
                )
                missing += 1
                continue
            content = path.read_bytes()
            if hashlib.sha256(content).hexdigest() != doc.sha256:
                logger.warning(
                    "file differs from kb.documents.sha256; chunking the file on disk",
                    extra={"document_id": str(doc.id), "source_path": doc.source_path},
                )
            rows = build_chunk_rows(doc, content.decode("utf-8"))
            if stored.get(doc.id, []) == [_fingerprint(r) for r in rows]:
                skipped += 1
                continue
            with conn.transaction():
                conn.execute("DELETE FROM kb.chunks WHERE document_id = %s", (doc.id,))
                with conn.cursor() as cur:
                    cur.executemany(_INSERT, [_params(r) for r in rows])
            ingested += 1
            written += len(rows)
    summary = IngestSummary(len(documents), ingested, skipped, missing, written)
    logger.info("documents ingested", extra={"summary": summary})
    return summary


type _Fingerprint = tuple[object, ...]


def _fingerprint(row: ChunkRow) -> _Fingerprint:
    return (
        row.id,
        row.ordinal,
        row.sha256,
        row.context_header,
        row.section_path,
        row.language,
        row.token_count,
        row.metadata,
    )


def _stored_chunks(conn: psycopg.Connection) -> dict[uuid.UUID, list[_Fingerprint]]:
    stored: dict[uuid.UUID, list[_Fingerprint]] = {}
    rows = conn.execute(
        "SELECT document_id, id, ordinal, sha256, context_header, section_path, language,"
        " token_count, metadata FROM kb.chunks ORDER BY document_id, ordinal"
    ).fetchall()
    for document_id, *fingerprint in rows:
        stored.setdefault(document_id, []).append(tuple(fingerprint))
    return stored


def _params(row: ChunkRow) -> tuple[object, ...]:
    return (
        row.id,
        row.document_id,
        row.ordinal,
        row.text,
        row.context_header,
        row.section_path,
        row.language,
        row.token_count,
        row.sha256,
        Jsonb(row.metadata),
    )
