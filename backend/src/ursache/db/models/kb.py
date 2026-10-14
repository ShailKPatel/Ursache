from __future__ import annotations

import uuid
from datetime import date, datetime
from typing import Any

import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from ursache.db.base import Base, created_at, uuid_pk

SCHEMA = "kb"


class Document(Base):
    __tablename__ = "documents"
    __table_args__ = (
        sa.Index("ix_documents_effective", "effective_from", "effective_to"),
        {"schema": SCHEMA},
    )

    id: Mapped[uuid.UUID] = uuid_pk()
    doc_type: Mapped[str] = mapped_column(sa.Text, index=True)
    title: Mapped[str] = mapped_column(sa.Text)
    language: Mapped[str] = mapped_column(sa.String(8))
    version: Mapped[str] = mapped_column(sa.Text)
    effective_from: Mapped[date] = mapped_column(sa.Date)
    effective_to: Mapped[date | None] = mapped_column(sa.Date)
    source_path: Mapped[str] = mapped_column(sa.Text)
    sha256: Mapped[str] = mapped_column(sa.String(64), unique=True)
    created_at: Mapped[datetime] = created_at()


class Chunk(Base):
    __tablename__ = "chunks"
    __table_args__ = (
        sa.UniqueConstraint("document_id", "ordinal", name="uq_chunks_document_id_ordinal"),
        {"schema": SCHEMA},
    )

    id: Mapped[uuid.UUID] = uuid_pk()
    document_id: Mapped[uuid.UUID] = mapped_column(
        sa.ForeignKey("kb.documents.id", ondelete="CASCADE")
    )
    ordinal: Mapped[int] = mapped_column(sa.Integer)
    text: Mapped[str] = mapped_column(sa.Text)
    context_header: Mapped[str] = mapped_column(sa.Text)
    section_path: Mapped[str] = mapped_column(sa.Text)
    page: Mapped[int | None] = mapped_column(sa.Integer)
    language: Mapped[str] = mapped_column(sa.String(8))
    token_count: Mapped[int] = mapped_column(sa.Integer)
    sha256: Mapped[str] = mapped_column(sa.String(64), index=True)
    metadata_: Mapped[dict[str, Any]] = mapped_column(
        "metadata", JSONB, server_default=sa.text("'{}'::jsonb")
    )
    created_at: Mapped[datetime] = created_at()


class Image(Base):
    __tablename__ = "images"
    __table_args__ = {"schema": SCHEMA}

    id: Mapped[uuid.UUID] = uuid_pk()
    object_key: Mapped[str] = mapped_column(sa.Text, unique=True)
    public_url: Mapped[str | None] = mapped_column(sa.Text)
    sha256: Mapped[str] = mapped_column(sa.String(64), unique=True)
    width: Mapped[int] = mapped_column(sa.Integer)
    height: Mapped[int] = mapped_column(sa.Integer)
    source_dataset: Mapped[str] = mapped_column(sa.Text)
    source_label: Mapped[str] = mapped_column(sa.Text)
    created_at: Mapped[datetime] = created_at()


class IndexState(Base):
    __tablename__ = "index_state"
    __table_args__ = {"schema": SCHEMA}

    item_type: Mapped[str] = mapped_column(sa.Text, primary_key=True)
    item_id: Mapped[uuid.UUID] = mapped_column(sa.Uuid, primary_key=True)
    collection: Mapped[str] = mapped_column(sa.Text, primary_key=True)
    model_version: Mapped[str] = mapped_column(sa.Text)
    indexed_at: Mapped[datetime] = mapped_column(
        sa.DateTime(timezone=True), server_default=sa.func.now()
    )
