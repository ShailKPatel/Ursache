from __future__ import annotations

import enum
import uuid
from datetime import datetime
from typing import Any

import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import ARRAY, JSONB
from sqlalchemy.orm import Mapped, mapped_column

from ursache.db.base import Base, created_at, str_enum, uuid_pk
from ursache.db.models.app import Category6M

SCHEMA = "eval"
_UUID_ARRAY: ARRAY[uuid.UUID] = ARRAY(sa.Uuid())


class QuestionKind(enum.StrEnum):
    RETRIEVAL = "retrieval"
    RCA = "rca"
    SQL = "sql"
    IMAGE = "image"


class RootCause(Base):
    __tablename__ = "root_causes"
    __table_args__ = {"schema": SCHEMA}

    id: Mapped[uuid.UUID] = uuid_pk()
    category_6m: Mapped[Category6M] = mapped_column(str_enum(Category6M, "category_6m"))
    mechanism: Mapped[str] = mapped_column(sa.Text)
    target_defect_class: Mapped[str] = mapped_column(sa.Text)
    created_at: Mapped[datetime] = created_at()


class Injection(Base):
    __tablename__ = "injections"
    __table_args__ = (
        sa.CheckConstraint("end_ts > start_ts", name="window_order"),
        sa.Index("ix_injections_line_id_start_ts", "line_id", "start_ts"),
        {"schema": SCHEMA},
    )

    id: Mapped[uuid.UUID] = uuid_pk()
    cause_id: Mapped[uuid.UUID] = mapped_column(sa.ForeignKey("eval.root_causes.id"), index=True)
    line_id: Mapped[uuid.UUID] = mapped_column(sa.ForeignKey("plant.lines.id"))
    equipment_id: Mapped[uuid.UUID | None] = mapped_column(
        sa.ForeignKey("plant.equipment.id"), index=True
    )
    start_ts: Mapped[datetime] = mapped_column(sa.DateTime(timezone=True))
    end_ts: Mapped[datetime] = mapped_column(sa.DateTime(timezone=True))
    params: Mapped[dict[str, Any]] = mapped_column(JSONB, server_default=sa.text("'{}'::jsonb"))


class Question(Base):
    __tablename__ = "questions"
    __table_args__ = {"schema": SCHEMA}

    id: Mapped[uuid.UUID] = uuid_pk()
    kind: Mapped[QuestionKind] = mapped_column(str_enum(QuestionKind, "question_kind"))
    query: Mapped[str] = mapped_column(sa.Text)
    incident_id: Mapped[uuid.UUID | None] = mapped_column(
        sa.ForeignKey("plant.incidents.id"), index=True
    )
    gold_chunk_ids: Mapped[list[uuid.UUID]] = mapped_column(
        _UUID_ARRAY, server_default=sa.text("'{}'::uuid[]")
    )
    gold_cause_id: Mapped[uuid.UUID | None] = mapped_column(
        sa.ForeignKey("eval.root_causes.id"), index=True
    )
    gold_answer: Mapped[str | None] = mapped_column(sa.Text)


class Run(Base):
    __tablename__ = "runs"
    __table_args__ = {"schema": SCHEMA}

    id: Mapped[uuid.UUID] = uuid_pk()
    git_sha: Mapped[str] = mapped_column(sa.String(40))
    config: Mapped[dict[str, Any]] = mapped_column(JSONB, server_default=sa.text("'{}'::jsonb"))
    started_at: Mapped[datetime] = mapped_column(
        sa.DateTime(timezone=True), server_default=sa.func.now(), index=True
    )


class Result(Base):
    __tablename__ = "results"
    __table_args__ = {"schema": SCHEMA}

    run_id: Mapped[uuid.UUID] = mapped_column(
        sa.ForeignKey("eval.runs.id", ondelete="CASCADE"), primary_key=True
    )
    question_id: Mapped[uuid.UUID] = mapped_column(
        sa.ForeignKey("eval.questions.id"), primary_key=True, index=True
    )
    metric: Mapped[str] = mapped_column(sa.Text, primary_key=True)
    value: Mapped[float] = mapped_column(sa.Double)
