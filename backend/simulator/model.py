"""Plain row types for everything the simulator writes, independent of the ORM."""

from __future__ import annotations

import hashlib
import uuid
from dataclasses import dataclass, field, fields
from datetime import date, datetime
from typing import NamedTuple

_NAMESPACE = uuid.uuid5(uuid.NAMESPACE_URL, "https://github.com/ShailKPatel/Ursache/simulator")


def stable_id(seed: int, *parts: object) -> uuid.UUID:
    """Same seed and parts give the same UUID, independent of generation order."""
    return uuid.uuid5(_NAMESPACE, "/".join(map(str, (seed, *parts))))


@dataclass(frozen=True, slots=True)
class LineRow:
    id: uuid.UUID
    name: str
    process_type: str


@dataclass(frozen=True, slots=True)
class EquipmentRow:
    id: uuid.UUID
    line_id: uuid.UUID
    tag: str
    type: str
    name: str


@dataclass(frozen=True, slots=True)
class SupplierRow:
    id: uuid.UUID
    name: str
    country: str


@dataclass(frozen=True, slots=True)
class GradeRow:
    id: uuid.UUID
    code: str
    spec: str


@dataclass(frozen=True, slots=True)
class LotRow:
    id: uuid.UUID
    supplier_id: uuid.UUID
    grade_id: uuid.UUID
    received_at: datetime
    cert_document_id: uuid.UUID | None


@dataclass(frozen=True, slots=True)
class CoilRow:
    id: uuid.UUID
    line_id: uuid.UUID
    lot_id: uuid.UUID
    grade_id: uuid.UUID
    shift: str
    crew: str
    started_at: datetime
    finished_at: datetime


class ReadingRow(NamedTuple):
    line_id: uuid.UUID
    equipment_id: uuid.UUID
    ts: datetime
    parameter: str
    value: float
    unit: str


@dataclass(frozen=True, slots=True)
class InspectionRow:
    id: uuid.UUID
    coil_id: uuid.UUID
    ts: datetime
    method: str
    result: str


@dataclass(frozen=True, slots=True)
class DefectRow:
    id: uuid.UUID
    inspection_id: uuid.UUID
    coil_id: uuid.UUID
    defect_class: str
    severity: int
    position_m: float


@dataclass(frozen=True, slots=True)
class MaintenanceRow:
    id: uuid.UUID
    equipment_id: uuid.UUID
    ts: datetime
    kind: str
    description: str
    technician: str


@dataclass(frozen=True, slots=True)
class IncidentRow:
    id: uuid.UUID
    title: str
    description: str
    line_id: uuid.UUID
    reported_at: datetime
    severity: int
    language: str


@dataclass(frozen=True, slots=True)
class DocumentRow:
    id: uuid.UUID
    doc_type: str
    title: str
    language: str
    version: str
    effective_from: date
    effective_to: date | None
    source_path: str
    sha256: str
    content: str = field(repr=False, compare=False)


@dataclass(frozen=True, slots=True)
class RootCauseRow:
    id: uuid.UUID
    category_6m: str
    mechanism: str
    target_defect_class: str


@dataclass(frozen=True, slots=True)
class InjectionRow:
    id: uuid.UUID
    cause_id: uuid.UUID
    line_id: uuid.UUID
    equipment_id: uuid.UUID | None
    start_ts: datetime
    end_ts: datetime
    params: dict[str, object]


@dataclass(frozen=True, slots=True)
class QuestionRow:
    id: uuid.UUID
    kind: str
    query: str
    incident_id: uuid.UUID | None
    gold_cause_id: uuid.UUID | None
    gold_answer: str | None
    # Reference query used by the tests to check gold_answer against the database; not stored.
    check_sql: str | None = field(default=None, compare=False)


@dataclass(slots=True)
class Dataset:
    lines: list[LineRow] = field(default_factory=list[LineRow])
    equipment: list[EquipmentRow] = field(default_factory=list[EquipmentRow])
    suppliers: list[SupplierRow] = field(default_factory=list[SupplierRow])
    grades: list[GradeRow] = field(default_factory=list[GradeRow])
    lots: list[LotRow] = field(default_factory=list[LotRow])
    coils: list[CoilRow] = field(default_factory=list[CoilRow])
    readings: list[ReadingRow] = field(default_factory=list[ReadingRow])
    inspections: list[InspectionRow] = field(default_factory=list[InspectionRow])
    defects: list[DefectRow] = field(default_factory=list[DefectRow])
    maintenance: list[MaintenanceRow] = field(default_factory=list[MaintenanceRow])
    incidents: list[IncidentRow] = field(default_factory=list[IncidentRow])
    documents: list[DocumentRow] = field(default_factory=list[DocumentRow])
    root_causes: list[RootCauseRow] = field(default_factory=list[RootCauseRow])
    injections: list[InjectionRow] = field(default_factory=list[InjectionRow])
    questions: list[QuestionRow] = field(default_factory=list[QuestionRow])

    def counts(self) -> dict[str, int]:
        return {f.name: len(getattr(self, f.name)) for f in fields(self)}

    def digest(self) -> str:
        """SHA-256 over every row and every document body, in generation order."""
        h = hashlib.sha256()
        for f in fields(self):
            h.update(f.name.encode())
            rows: list[object] = getattr(self, f.name)
            for row in rows:
                h.update(repr(row).encode())
        for doc in self.documents:
            h.update(doc.content.encode())
        return h.hexdigest()
