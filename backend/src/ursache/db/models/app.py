from __future__ import annotations

import enum
import uuid
from datetime import date, datetime
from typing import Any

import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from ursache.db.base import Base, created_at, str_enum, uuid_pk

SCHEMA = "app"


class UserRole(enum.StrEnum):
    ENGINEER = "engineer"
    MANAGER = "manager"
    ADMIN = "admin"


class InvestigationStatus(enum.StrEnum):
    RUNNING = "running"
    AWAITING_REVIEW = "awaiting_review"
    COMPLETED = "completed"
    FAILED = "failed"


class EvidenceSourceType(enum.StrEnum):
    CHUNK = "chunk"
    IMAGE = "image"
    SQL = "sql"
    DEFECT = "defect"


class Category6M(enum.StrEnum):
    MAN = "man"
    MACHINE = "machine"
    METHOD = "method"
    MATERIAL = "material"
    MEASUREMENT = "measurement"
    ENVIRONMENT = "environment"


class HypothesisStatus(enum.StrEnum):
    PROPOSED = "proposed"
    ACCEPTED = "accepted"
    REJECTED = "rejected"


class Stance(enum.StrEnum):
    SUPPORTS = "supports"
    CONTRADICTS = "contradicts"


class User(Base):
    __tablename__ = "users"
    __table_args__ = {"schema": SCHEMA}

    id: Mapped[uuid.UUID] = uuid_pk()
    name: Mapped[str] = mapped_column(sa.Text, unique=True)
    role: Mapped[UserRole] = mapped_column(str_enum(UserRole, "user_role"))
    created_at: Mapped[datetime] = created_at()


class Investigation(Base):
    __tablename__ = "investigations"
    __table_args__ = {"schema": SCHEMA}

    id: Mapped[uuid.UUID] = uuid_pk()
    incident_id: Mapped[uuid.UUID] = mapped_column(sa.ForeignKey("plant.incidents.id"), index=True)
    created_by: Mapped[uuid.UUID | None] = mapped_column(sa.ForeignKey("app.users.id"), index=True)
    status: Mapped[InvestigationStatus] = mapped_column(
        str_enum(InvestigationStatus, "investigation_status"),
        server_default=InvestigationStatus.RUNNING.value,
    )
    is_replay: Mapped[bool] = mapped_column(sa.Boolean, server_default=sa.false())
    config: Mapped[dict[str, Any]] = mapped_column(JSONB, server_default=sa.text("'{}'::jsonb"))
    started_at: Mapped[datetime] = mapped_column(
        sa.DateTime(timezone=True), server_default=sa.func.now(), index=True
    )
    finished_at: Mapped[datetime | None] = mapped_column(sa.DateTime(timezone=True))


class Step(Base):
    __tablename__ = "steps"
    __table_args__ = (
        sa.UniqueConstraint("investigation_id", "step_no", name="uq_steps_investigation_step"),
        {"schema": SCHEMA},
    )

    id: Mapped[uuid.UUID] = uuid_pk()
    investigation_id: Mapped[uuid.UUID] = mapped_column(
        sa.ForeignKey("app.investigations.id", ondelete="CASCADE")
    )
    step_no: Mapped[int] = mapped_column(sa.Integer)
    node: Mapped[str] = mapped_column(sa.Text)
    tool: Mapped[str | None] = mapped_column(sa.Text)
    input: Mapped[dict[str, Any]] = mapped_column(JSONB, server_default=sa.text("'{}'::jsonb"))
    output_summary: Mapped[str | None] = mapped_column(sa.Text)
    latency_ms: Mapped[int | None] = mapped_column(sa.Integer)
    tokens_in: Mapped[int | None] = mapped_column(sa.Integer)
    tokens_out: Mapped[int | None] = mapped_column(sa.Integer)
    created_at: Mapped[datetime] = created_at()


class Evidence(Base):
    __tablename__ = "evidence"
    __table_args__ = {"schema": SCHEMA}

    id: Mapped[uuid.UUID] = uuid_pk()
    investigation_id: Mapped[uuid.UUID] = mapped_column(
        sa.ForeignKey("app.investigations.id", ondelete="CASCADE"), index=True
    )
    source_type: Mapped[EvidenceSourceType] = mapped_column(
        str_enum(EvidenceSourceType, "evidence_source_type")
    )
    source_id: Mapped[str] = mapped_column(sa.Text)
    snapshot: Mapped[dict[str, Any]] = mapped_column(JSONB)
    retrieval_score: Mapped[float | None] = mapped_column(sa.Double)
    rerank_score: Mapped[float | None] = mapped_column(sa.Double)
    created_at: Mapped[datetime] = created_at()


class Hypothesis(Base):
    __tablename__ = "hypotheses"
    __table_args__ = (
        sa.CheckConstraint("confidence BETWEEN 0 AND 1", name="confidence_range"),
        {"schema": SCHEMA},
    )

    id: Mapped[uuid.UUID] = uuid_pk()
    investigation_id: Mapped[uuid.UUID] = mapped_column(
        sa.ForeignKey("app.investigations.id", ondelete="CASCADE"), index=True
    )
    category_6m: Mapped[Category6M] = mapped_column(str_enum(Category6M, "category_6m"))
    statement: Mapped[str] = mapped_column(sa.Text)
    confidence: Mapped[float] = mapped_column(sa.Double)
    status: Mapped[HypothesisStatus] = mapped_column(
        str_enum(HypothesisStatus, "hypothesis_status"),
        server_default=HypothesisStatus.PROPOSED.value,
    )
    reviewer_note: Mapped[str | None] = mapped_column(sa.Text)
    created_at: Mapped[datetime] = created_at()


class HypothesisEvidence(Base):
    __tablename__ = "hypothesis_evidence"
    __table_args__ = {"schema": SCHEMA}

    hypothesis_id: Mapped[uuid.UUID] = mapped_column(
        sa.ForeignKey("app.hypotheses.id", ondelete="CASCADE"), primary_key=True
    )
    evidence_id: Mapped[uuid.UUID] = mapped_column(
        sa.ForeignKey("app.evidence.id", ondelete="CASCADE"), primary_key=True, index=True
    )
    stance: Mapped[Stance] = mapped_column(str_enum(Stance, "stance"))


class Report(Base):
    __tablename__ = "reports"
    __table_args__ = {"schema": SCHEMA}

    id: Mapped[uuid.UUID] = uuid_pk()
    investigation_id: Mapped[uuid.UUID] = mapped_column(
        sa.ForeignKey("app.investigations.id", ondelete="CASCADE"), index=True
    )
    markdown: Mapped[str] = mapped_column(sa.Text)
    grounding_score: Mapped[float | None] = mapped_column(sa.Double)
    created_at: Mapped[datetime] = created_at()


class LLMCacheEntry(Base):
    __tablename__ = "llm_cache"
    __table_args__ = {"schema": SCHEMA}

    key: Mapped[str] = mapped_column(sa.String(64), primary_key=True)
    model: Mapped[str] = mapped_column(sa.Text)
    response: Mapped[dict[str, Any]] = mapped_column(JSONB)
    tokens_in: Mapped[int] = mapped_column(sa.Integer)
    tokens_out: Mapped[int] = mapped_column(sa.Integer)
    created_at: Mapped[datetime] = created_at()


class QuotaUsage(Base):
    __tablename__ = "quota_usage"
    __table_args__ = {"schema": SCHEMA}

    day: Mapped[date] = mapped_column(sa.Date, primary_key=True)
    provider: Mapped[str] = mapped_column(sa.Text, primary_key=True)
    model: Mapped[str] = mapped_column(sa.Text, primary_key=True)
    requests: Mapped[int] = mapped_column(sa.Integer, server_default="0")
    tokens: Mapped[int] = mapped_column(sa.BigInteger, server_default="0")
