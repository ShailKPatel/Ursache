from __future__ import annotations

import enum
import uuid
from datetime import datetime

import sqlalchemy as sa
from sqlalchemy.orm import Mapped, mapped_column

from ursache.db.base import Base, created_at, str_enum, uuid_pk

SCHEMA = "plant"


class MaintenanceKind(enum.StrEnum):
    PLANNED = "planned"
    UNPLANNED = "unplanned"


class IncidentStatus(enum.StrEnum):
    OPEN = "open"
    INVESTIGATING = "investigating"
    CLOSED = "closed"


class Line(Base):
    __tablename__ = "lines"
    __table_args__ = {"schema": SCHEMA}

    id: Mapped[uuid.UUID] = uuid_pk()
    name: Mapped[str] = mapped_column(sa.Text, unique=True)
    process_type: Mapped[str] = mapped_column(sa.Text)
    created_at: Mapped[datetime] = created_at()


class Equipment(Base):
    __tablename__ = "equipment"
    __table_args__ = {"schema": SCHEMA}

    id: Mapped[uuid.UUID] = uuid_pk()
    line_id: Mapped[uuid.UUID] = mapped_column(sa.ForeignKey("plant.lines.id"), index=True)
    tag: Mapped[str] = mapped_column(sa.Text, unique=True)
    type: Mapped[str] = mapped_column(sa.Text)
    name: Mapped[str] = mapped_column(sa.Text)
    created_at: Mapped[datetime] = created_at()


class Supplier(Base):
    __tablename__ = "suppliers"
    __table_args__ = {"schema": SCHEMA}

    id: Mapped[uuid.UUID] = uuid_pk()
    name: Mapped[str] = mapped_column(sa.Text, unique=True)
    country: Mapped[str] = mapped_column(sa.String(2))
    created_at: Mapped[datetime] = created_at()


class SteelGrade(Base):
    __tablename__ = "steel_grades"
    __table_args__ = {"schema": SCHEMA}

    id: Mapped[uuid.UUID] = uuid_pk()
    code: Mapped[str] = mapped_column(sa.Text, unique=True)
    spec: Mapped[str] = mapped_column(sa.Text)
    created_at: Mapped[datetime] = created_at()


class MaterialLot(Base):
    __tablename__ = "material_lots"
    __table_args__ = {"schema": SCHEMA}

    id: Mapped[uuid.UUID] = uuid_pk()
    supplier_id: Mapped[uuid.UUID] = mapped_column(sa.ForeignKey("plant.suppliers.id"), index=True)
    grade_id: Mapped[uuid.UUID] = mapped_column(sa.ForeignKey("plant.steel_grades.id"), index=True)
    received_at: Mapped[datetime] = mapped_column(sa.DateTime(timezone=True), index=True)
    cert_document_id: Mapped[uuid.UUID | None] = mapped_column(
        sa.ForeignKey("kb.documents.id"), index=True
    )
    created_at: Mapped[datetime] = created_at()


class Coil(Base):
    __tablename__ = "coils"
    __table_args__ = (
        sa.Index("ix_coils_line_id_started_at", "line_id", "started_at"),
        {"schema": SCHEMA},
    )

    id: Mapped[uuid.UUID] = uuid_pk()
    line_id: Mapped[uuid.UUID] = mapped_column(sa.ForeignKey("plant.lines.id"))
    lot_id: Mapped[uuid.UUID] = mapped_column(sa.ForeignKey("plant.material_lots.id"), index=True)
    grade_id: Mapped[uuid.UUID] = mapped_column(sa.ForeignKey("plant.steel_grades.id"), index=True)
    shift: Mapped[str] = mapped_column(sa.Text)
    crew: Mapped[str] = mapped_column(sa.Text)
    started_at: Mapped[datetime] = mapped_column(sa.DateTime(timezone=True))
    finished_at: Mapped[datetime | None] = mapped_column(sa.DateTime(timezone=True))
    created_at: Mapped[datetime] = created_at()


class ProcessReading(Base):
    __tablename__ = "process_readings"
    __table_args__ = (
        sa.Index("ix_process_readings_equipment_parameter_ts", "equipment_id", "parameter", "ts"),
        sa.Index("ix_process_readings_line_id_ts", "line_id", "ts"),
        {"schema": SCHEMA},
    )

    id: Mapped[int] = mapped_column(sa.BigInteger, sa.Identity(always=True), primary_key=True)
    line_id: Mapped[uuid.UUID] = mapped_column(sa.ForeignKey("plant.lines.id"))
    equipment_id: Mapped[uuid.UUID] = mapped_column(sa.ForeignKey("plant.equipment.id"))
    ts: Mapped[datetime] = mapped_column(sa.DateTime(timezone=True))
    parameter: Mapped[str] = mapped_column(sa.Text)
    value: Mapped[float] = mapped_column(sa.Double)
    unit: Mapped[str] = mapped_column(sa.Text)


class Inspection(Base):
    __tablename__ = "inspections"
    __table_args__ = {"schema": SCHEMA}

    id: Mapped[uuid.UUID] = uuid_pk()
    coil_id: Mapped[uuid.UUID] = mapped_column(sa.ForeignKey("plant.coils.id"), index=True)
    ts: Mapped[datetime] = mapped_column(sa.DateTime(timezone=True), index=True)
    method: Mapped[str] = mapped_column(sa.Text)
    result: Mapped[str] = mapped_column(sa.Text)


class Defect(Base):
    __tablename__ = "defects"
    __table_args__ = (
        sa.CheckConstraint("severity BETWEEN 1 AND 5", name="severity_range"),
        {"schema": SCHEMA},
    )

    id: Mapped[uuid.UUID] = uuid_pk()
    inspection_id: Mapped[uuid.UUID] = mapped_column(
        sa.ForeignKey("plant.inspections.id"), index=True
    )
    coil_id: Mapped[uuid.UUID] = mapped_column(sa.ForeignKey("plant.coils.id"), index=True)
    defect_class: Mapped[str] = mapped_column(sa.Text, index=True)
    severity: Mapped[int] = mapped_column(sa.SmallInteger)
    position_m: Mapped[float] = mapped_column(sa.Double)
    image_id: Mapped[uuid.UUID | None] = mapped_column(sa.ForeignKey("kb.images.id"), index=True)
    created_at: Mapped[datetime] = created_at()


class MaintenanceEvent(Base):
    __tablename__ = "maintenance_events"
    __table_args__ = (
        sa.Index("ix_maintenance_events_equipment_id_ts", "equipment_id", "ts"),
        {"schema": SCHEMA},
    )

    id: Mapped[uuid.UUID] = uuid_pk()
    equipment_id: Mapped[uuid.UUID] = mapped_column(sa.ForeignKey("plant.equipment.id"))
    ts: Mapped[datetime] = mapped_column(sa.DateTime(timezone=True))
    kind: Mapped[MaintenanceKind] = mapped_column(str_enum(MaintenanceKind, "maintenance_kind"))
    description: Mapped[str] = mapped_column(sa.Text)
    technician: Mapped[str] = mapped_column(sa.Text)


class Incident(Base):
    __tablename__ = "incidents"
    __table_args__ = (
        sa.CheckConstraint("severity BETWEEN 1 AND 5", name="severity_range"),
        sa.Index("ix_incidents_line_id_reported_at", "line_id", "reported_at"),
        {"schema": SCHEMA},
    )

    id: Mapped[uuid.UUID] = uuid_pk()
    title: Mapped[str] = mapped_column(sa.Text)
    description: Mapped[str] = mapped_column(sa.Text)
    line_id: Mapped[uuid.UUID] = mapped_column(sa.ForeignKey("plant.lines.id"))
    reported_at: Mapped[datetime] = mapped_column(sa.DateTime(timezone=True))
    severity: Mapped[int] = mapped_column(sa.SmallInteger)
    status: Mapped[IncidentStatus] = mapped_column(
        str_enum(IncidentStatus, "incident_status"), server_default=IncidentStatus.OPEN.value
    )
    language: Mapped[str] = mapped_column(sa.String(8))
    created_at: Mapped[datetime] = created_at()
