"""Persist a generated dataset: Markdown files on disk, rows in Postgres via COPY."""

from __future__ import annotations

import logging
import uuid
from collections.abc import Iterable, Sequence
from dataclasses import dataclass, replace
from operator import attrgetter
from pathlib import Path

import psycopg
from psycopg import sql
from psycopg.types.json import Jsonb

from simulator.config import SimConfig
from simulator.generate import generate
from simulator.model import Dataset

logger = logging.getLogger(__name__)

DOC_TYPES: tuple[str, ...] = (
    "work_instruction",
    "sop",
    "maintenance_manual",
    "material_certificate",
    "8d_report",
)
DOC_DIRS: tuple[str, ...] = (
    "work_instructions",
    "sops",
    "maintenance_manual",
    "certificates",
    "8d_reports",
)

# Insert order respects foreign keys; documents are inserted separately before material_lots.
_TABLES: tuple[tuple[str, str, tuple[str, ...]], ...] = (
    ("lines", "plant.lines", ("id", "name", "process_type")),
    ("equipment", "plant.equipment", ("id", "line_id", "tag", "type", "name")),
    ("suppliers", "plant.suppliers", ("id", "name", "country")),
    ("grades", "plant.steel_grades", ("id", "code", "spec")),
    (
        "lots",
        "plant.material_lots",
        ("id", "supplier_id", "grade_id", "received_at", "cert_document_id"),
    ),
    (
        "coils",
        "plant.coils",
        ("id", "line_id", "lot_id", "grade_id", "shift", "crew", "started_at", "finished_at"),
    ),
    (
        "readings",
        "plant.process_readings",
        ("line_id", "equipment_id", "ts", "parameter", "value", "unit"),
    ),
    ("inspections", "plant.inspections", ("id", "coil_id", "ts", "method", "result")),
    (
        "defects",
        "plant.defects",
        ("id", "inspection_id", "coil_id", "defect_class", "severity", "position_m"),
    ),
    (
        "maintenance",
        "plant.maintenance_events",
        ("id", "equipment_id", "ts", "kind", "description", "technician"),
    ),
    (
        "incidents",
        "plant.incidents",
        ("id", "title", "description", "line_id", "reported_at", "severity", "language"),
    ),
    ("root_causes", "eval.root_causes", ("id", "category_6m", "mechanism", "target_defect_class")),
    (
        "injections",
        "eval.injections",
        ("id", "cause_id", "line_id", "equipment_id", "start_ts", "end_ts", "params"),
    ),
    (
        "questions",
        "eval.questions",
        ("id", "kind", "query", "incident_id", "gold_cause_id", "gold_answer"),
    ),
)


class SimulatorError(RuntimeError):
    pass


@dataclass(frozen=True, slots=True)
class Summary:
    counts: dict[str, int]
    digest: str
    size_mb: float


def simulate(cfg: SimConfig, database_url: str, docs_dir: Path, *, reset: bool) -> Summary:
    """Generate, write documents and rows, refresh the coil summary view."""
    with psycopg.connect(database_url) as conn:
        _check_target(conn, reset=reset)
        ds = generate(cfg)
        write_documents(ds, docs_dir)
        load(conn, ds)
        size = database_size_mb(conn)
    return Summary(ds.counts(), ds.digest(), size)


def write_documents(ds: Dataset, root: Path) -> None:
    """Replace the simulator's Markdown files under root (other files are left alone)."""
    for sub in DOC_DIRS:
        for stale in (root / sub).glob("*.md"):
            stale.unlink()
    for doc in ds.documents:
        path = root / doc.source_path
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(doc.content.encode("utf-8"))
    logger.info("documents written", extra={"count": len(ds.documents), "root": str(root)})


def _check_target(conn: psycopg.Connection, *, reset: bool) -> None:
    if reset:
        reset_tables(conn)
        return
    row = conn.execute("SELECT EXISTS (SELECT 1 FROM plant.coils)").fetchone()
    if row is not None and row[0]:
        raise SimulatorError("plant already contains simulated data; rerun with --reset")


def reset_tables(conn: psycopg.Connection) -> None:
    """Delete what the simulator writes. Fails instead of orphaning investigations."""
    row = conn.execute("SELECT count(*) FROM app.investigations").fetchone()
    if row is not None and row[0]:
        raise SimulatorError(f"{row[0]} investigation(s) reference incidents; delete them first")
    conn.execute(
        "DELETE FROM eval.results WHERE question_id IN"
        " (SELECT id FROM eval.questions WHERE kind IN ('rca', 'sql'))"
    )
    conn.execute("DELETE FROM eval.questions WHERE kind IN ('rca', 'sql')")
    conn.execute(
        "TRUNCATE plant.process_readings, plant.defects, plant.inspections,"
        " plant.maintenance_events"
    )
    for table in (
        "eval.injections",
        "eval.root_causes",
        "plant.incidents",
        "plant.coils",
        "plant.material_lots",
        "plant.equipment",
        "plant.lines",
        "plant.suppliers",
        "plant.steel_grades",
    ):
        conn.execute(sql.SQL("DELETE FROM {}").format(sql.Identifier(*table.split("."))))
    conn.execute("DELETE FROM kb.documents WHERE doc_type = ANY(%s)", (list(DOC_TYPES),))
    logger.info("simulator tables cleared")


def load(conn: psycopg.Connection, ds: Dataset) -> None:
    """Insert every row in one transaction, then refresh plant.coil_process_summary."""
    doc_ids = _upsert_documents(conn, ds)
    for attr, table, columns in _TABLES:
        rows: Sequence[object] = getattr(ds, attr)
        if attr == "lots":
            rows = [
                replace(lot, cert_document_id=doc_ids.get(lot.cert_document_id))
                if lot.cert_document_id
                else lot
                for lot in ds.lots
            ]
        _copy(conn, table, columns, rows)
    conn.execute("REFRESH MATERIALIZED VIEW plant.coil_process_summary")
    conn.commit()
    logger.info("dataset loaded", extra={"counts": ds.counts()})


def _upsert_documents(conn: psycopg.Connection, ds: Dataset) -> dict[uuid.UUID, uuid.UUID]:
    """Insert documents keyed by sha256; returns generated id -> stored id."""
    stored: dict[uuid.UUID, uuid.UUID] = {}
    with conn.cursor() as cur:
        for doc in ds.documents:
            cur.execute(
                "INSERT INTO kb.documents (id, doc_type, title, language, version,"
                " effective_from, effective_to, source_path, sha256)"
                " VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)"
                " ON CONFLICT (sha256) DO UPDATE SET source_path = EXCLUDED.source_path"
                " RETURNING id",
                (
                    doc.id,
                    doc.doc_type,
                    doc.title,
                    doc.language,
                    doc.version,
                    doc.effective_from,
                    doc.effective_to,
                    doc.source_path,
                    doc.sha256,
                ),
            )
            row = cur.fetchone()
            assert row is not None
            stored[doc.id] = row[0]
    return stored


def _copy(
    conn: psycopg.Connection, table: str, columns: tuple[str, ...], rows: Iterable[object]
) -> None:
    get = attrgetter(*columns)
    statement = sql.SQL("COPY {} ({}) FROM STDIN").format(
        sql.Identifier(*table.split(".")), sql.SQL(", ").join(map(sql.Identifier, columns))
    )
    with conn.cursor() as cur, cur.copy(statement) as copy:
        for row in rows:
            values: tuple[object, ...] = get(row)
            copy.write_row([Jsonb(v) if isinstance(v, dict) else v for v in values])


def database_size_mb(conn: psycopg.Connection) -> float:
    """Total on-disk size of plant, kb and eval, including indexes and TOAST."""
    row = conn.execute(
        "SELECT coalesce(sum(pg_total_relation_size(c.oid)), 0)::bigint FROM pg_class c"
        " JOIN pg_namespace n ON n.oid = c.relnamespace"
        " WHERE n.nspname IN ('plant', 'kb', 'eval') AND c.relkind IN ('r', 'm')"
    ).fetchone()
    return round((row[0] if row else 0) / 1_048_576, 1)
