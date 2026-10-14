import logging
from collections.abc import Iterator
from pathlib import Path

import psycopg
import pytest

from simulator import SimConfig, simulate
from simulator.writer import reset_tables
from ursache.config import Settings
from ursache.db import admin
from ursache.ingestion import IngestionError, IngestSummary, ingest_documents
from ursache.ingestion.chunking import MAX_TOKENS

pytestmark = pytest.mark.integration

CONFIG = SimConfig(seed=42, days=21, coils_per_day=12, samples_per_coil=1)
FIXED_DOCS = {"work_instruction": 5, "sop": 4, "maintenance_manual": 5, "8d_report": 4}
CHUNKS_PER_DOC = (1, 3)

type ChunkKey = tuple[object, ...]


def connect(url: str) -> psycopg.Connection:
    return psycopg.connect(admin.libpq_url(url), autocommit=True)


def ingest(settings: Settings, docs_dir: Path, *, force: bool = False) -> IngestSummary:
    return ingest_documents(admin.libpq_url(settings.app_database_url), docs_dir, force=force)


def chunk_keys(settings: Settings) -> list[ChunkKey]:
    with connect(settings.migration_database_url) as conn:
        rows = conn.execute("SELECT id, document_id, sha256 FROM kb.chunks ORDER BY id")
        return [tuple(r) for r in rows]


@pytest.fixture(scope="module")
def docs_dir(tmp_path_factory: pytest.TempPathFactory) -> Path:
    return tmp_path_factory.mktemp("ingest-docs")


@pytest.fixture(scope="module")
def first_run(settings: Settings, docs_dir: Path) -> Iterator[IngestSummary]:
    url = admin.libpq_url(settings.migration_database_url)
    simulate(CONFIG, url, docs_dir, reset=True)
    yield ingest(settings, docs_dir)
    with psycopg.connect(url) as conn:
        reset_tables(conn)


def test_every_document_gets_chunks(settings: Settings, first_run: IngestSummary) -> None:
    assert first_run.missing == first_run.skipped == 0
    assert first_run.ingested == first_run.documents > sum(FIXED_DOCS.values())
    with connect(settings.migration_database_url) as conn:
        rows = conn.execute(
            "SELECT d.doc_type, count(DISTINCT d.id), count(c.id), max(c.token_count),"
            " count(*) FILTER (WHERE c.id IS NULL) FROM kb.documents d"
            " LEFT JOIN kb.chunks c ON c.document_id = d.id GROUP BY d.doc_type"
        ).fetchall()
        total = conn.execute("SELECT count(*) FROM kb.chunks").fetchone()
    per_type = {t: (docs, chunks, longest, empty) for t, docs, chunks, longest, empty in rows}
    assert set(per_type) == {*FIXED_DOCS, "material_certificate"}
    for doc_type, (docs, chunks, longest, empty) in per_type.items():
        assert docs == FIXED_DOCS.get(doc_type, docs), doc_type
        low, high = CHUNKS_PER_DOC
        assert low * docs <= chunks <= high * docs, (doc_type, docs, chunks)
        assert longest <= MAX_TOKENS
        assert empty == 0
    assert total is not None
    assert total[0] == first_run.chunks


def test_chunks_carry_language_and_filter_metadata(
    settings: Settings, first_run: IngestSummary
) -> None:
    with connect(settings.migration_database_url) as conn:
        mismatched = conn.execute(
            "SELECT count(*) FROM kb.chunks c JOIN kb.documents d ON d.id = c.document_id"
            " WHERE c.language <> d.language OR c.page IS NOT NULL"
            " OR c.metadata->>'doc_type' <> d.doc_type OR c.metadata->>'version' <> d.version"
            " OR (c.metadata->>'effective_from')::date <> d.effective_from"
            " OR (c.metadata->>'effective_to')::date IS DISTINCT FROM d.effective_to"
        ).fetchone()
        german = conn.execute("SELECT count(*) FROM kb.chunks WHERE language = 'de'").fetchone()
    assert mismatched == (0,)
    assert german is not None
    assert german[0] > 0


def test_rerun_skips_unchanged_documents(
    settings: Settings, first_run: IngestSummary, docs_dir: Path
) -> None:
    before = chunk_keys(settings)
    again = ingest(settings, docs_dir)
    assert again == IngestSummary(first_run.documents, 0, first_run.documents, 0, 0)
    assert chunk_keys(settings) == before


def test_force_rebuilds_identical_chunks(
    settings: Settings, first_run: IngestSummary, docs_dir: Path
) -> None:
    before = chunk_keys(settings)
    forced = ingest(settings, docs_dir, force=True)
    assert forced.ingested == forced.documents == first_run.documents
    assert forced.chunks == first_run.chunks
    assert chunk_keys(settings) == before


def test_changed_file_replaces_only_its_chunks(
    settings: Settings, first_run: IngestSummary, docs_dir: Path
) -> None:
    path = docs_dir / "sops" / "SOP-PRD-001_rev5.md"
    original = path.read_bytes()
    try:
        path.write_bytes(original + b"\n## 3 Records\n\nKeep the handover sheet for a year.\n")
        changed = ingest(settings, docs_dir)
        assert (changed.ingested, changed.skipped) == (1, first_run.documents - 1)
        with connect(settings.migration_database_url) as conn:
            hits = conn.execute(
                "SELECT count(*) FROM kb.chunks WHERE text LIKE '%handover sheet%'"
            ).fetchone()
        assert hits == (1,)
    finally:
        path.write_bytes(original)
        ingest(settings, docs_dir)


def test_missing_file_is_skipped_with_a_warning(
    settings: Settings,
    first_run: IngestSummary,
    docs_dir: Path,
    caplog: pytest.LogCaptureFixture,
) -> None:
    path = docs_dir / "8d_reports" / "8D-2025-031.md"
    original = path.read_bytes()
    path.unlink()
    try:
        with caplog.at_level(logging.WARNING, logger="ursache.ingestion"):
            result = ingest(settings, docs_dir, force=True)
        assert result.missing == 1
        assert result.ingested == first_run.documents - 1
        assert any("missing" in r.getMessage() for r in caplog.records)
    finally:
        path.write_bytes(original)


def test_missing_directory_is_an_error(settings: Settings, tmp_path: Path) -> None:
    with pytest.raises(IngestionError, match="not found"):
        ingest(settings, tmp_path / "absent")


def test_agent_reads_chunks_but_cannot_write(settings: Settings, first_run: IngestSummary) -> None:
    with connect(settings.agent_database_url) as conn:
        row = conn.execute("SELECT count(*) FROM kb.chunks").fetchone()
        assert row == (first_run.chunks,)
        with pytest.raises(psycopg.errors.ReadOnlySqlTransaction):
            conn.execute("DELETE FROM kb.chunks")
