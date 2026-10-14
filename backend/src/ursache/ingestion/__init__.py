"""Document ingestion: Markdown files referenced by kb.documents become kb.chunks rows."""

from ursache.ingestion.chunking import Chunk, approx_tokens, chunk_document, split_markdown
from ursache.ingestion.documents import (
    DocumentInfo,
    IngestionError,
    IngestSummary,
    build_chunk_rows,
    ingest_documents,
)

__all__ = [
    "Chunk",
    "DocumentInfo",
    "IngestSummary",
    "IngestionError",
    "approx_tokens",
    "build_chunk_rows",
    "chunk_document",
    "ingest_documents",
    "split_markdown",
]
