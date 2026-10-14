# pyright: basic
"""initial schema: plant, kb, app, eval tables and coil_process_summary

Revision ID: 0001
Revises:
Create Date: 2026-10-14 17:49:27.246920
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

from ursache.db.base import SCHEMAS
from ursache.db.views import coil_process_summary_sql

revision: str = "0001"
down_revision: str | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # Schemas are also created by roles.sql; whichever runs first wins.
    for schema in SCHEMAS:
        op.execute(f"CREATE SCHEMA IF NOT EXISTS {schema}")

    op.create_table(
        "llm_cache",
        sa.Column("key", sa.String(length=64), nullable=False),
        sa.Column("model", sa.Text(), nullable=False),
        sa.Column("response", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("tokens_in", sa.Integer(), nullable=False),
        sa.Column("tokens_out", sa.Integer(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("key", name=op.f("pk_llm_cache")),
        schema="app",
    )
    op.create_table(
        "quota_usage",
        sa.Column("day", sa.Date(), nullable=False),
        sa.Column("provider", sa.Text(), nullable=False),
        sa.Column("model", sa.Text(), nullable=False),
        sa.Column("requests", sa.Integer(), server_default="0", nullable=False),
        sa.Column("tokens", sa.BigInteger(), server_default="0", nullable=False),
        sa.PrimaryKeyConstraint("day", "provider", "model", name=op.f("pk_quota_usage")),
        schema="app",
    )
    op.create_table(
        "users",
        sa.Column("id", sa.Uuid(), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column("name", sa.Text(), nullable=False),
        sa.Column(
            "role",
            sa.Enum(
                "engineer",
                "manager",
                "admin",
                name="user_role",
                native_enum=False,
                create_constraint=False,
                length=32,
            ),
            nullable=False,
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.CheckConstraint(
            "role IN ('engineer', 'manager', 'admin')", name=op.f("ck_users_user_role")
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_users")),
        sa.UniqueConstraint("name", name=op.f("uq_users_name")),
        schema="app",
    )
    op.create_table(
        "root_causes",
        sa.Column("id", sa.Uuid(), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column(
            "category_6m",
            sa.Enum(
                "man",
                "machine",
                "method",
                "material",
                "measurement",
                "environment",
                name="category_6m",
                native_enum=False,
                create_constraint=False,
                length=32,
            ),
            nullable=False,
        ),
        sa.Column("mechanism", sa.Text(), nullable=False),
        sa.Column("target_defect_class", sa.Text(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.CheckConstraint(
            "category_6m IN ('man', 'machine', 'method', 'material', 'measurement', 'environment')",
            name=op.f("ck_root_causes_category_6m"),
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_root_causes")),
        schema="eval",
    )
    op.create_table(
        "runs",
        sa.Column("id", sa.Uuid(), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column("git_sha", sa.String(length=40), nullable=False),
        sa.Column(
            "config",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default=sa.text("'{}'::jsonb"),
            nullable=False,
        ),
        sa.Column(
            "started_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_runs")),
        schema="eval",
    )
    op.create_index(
        op.f("ix_eval_runs_started_at"), "runs", ["started_at"], unique=False, schema="eval"
    )
    op.create_table(
        "documents",
        sa.Column("id", sa.Uuid(), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column("doc_type", sa.Text(), nullable=False),
        sa.Column("title", sa.Text(), nullable=False),
        sa.Column("language", sa.String(length=8), nullable=False),
        sa.Column("version", sa.Text(), nullable=False),
        sa.Column("effective_from", sa.Date(), nullable=False),
        sa.Column("effective_to", sa.Date(), nullable=True),
        sa.Column("source_path", sa.Text(), nullable=False),
        sa.Column("sha256", sa.String(length=64), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_documents")),
        sa.UniqueConstraint("sha256", name=op.f("uq_documents_sha256")),
        schema="kb",
    )
    op.create_index(
        "ix_documents_effective",
        "documents",
        ["effective_from", "effective_to"],
        unique=False,
        schema="kb",
    )
    op.create_index(
        op.f("ix_kb_documents_doc_type"), "documents", ["doc_type"], unique=False, schema="kb"
    )
    op.create_table(
        "images",
        sa.Column("id", sa.Uuid(), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column("object_key", sa.Text(), nullable=False),
        sa.Column("public_url", sa.Text(), nullable=True),
        sa.Column("sha256", sa.String(length=64), nullable=False),
        sa.Column("width", sa.Integer(), nullable=False),
        sa.Column("height", sa.Integer(), nullable=False),
        sa.Column("source_dataset", sa.Text(), nullable=False),
        sa.Column("source_label", sa.Text(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_images")),
        sa.UniqueConstraint("object_key", name=op.f("uq_images_object_key")),
        sa.UniqueConstraint("sha256", name=op.f("uq_images_sha256")),
        schema="kb",
    )
    op.create_table(
        "index_state",
        sa.Column("item_type", sa.Text(), nullable=False),
        sa.Column("item_id", sa.Uuid(), nullable=False),
        sa.Column("collection", sa.Text(), nullable=False),
        sa.Column("model_version", sa.Text(), nullable=False),
        sa.Column(
            "indexed_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("item_type", "item_id", "collection", name=op.f("pk_index_state")),
        schema="kb",
    )
    op.create_table(
        "lines",
        sa.Column("id", sa.Uuid(), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column("name", sa.Text(), nullable=False),
        sa.Column("process_type", sa.Text(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_lines")),
        sa.UniqueConstraint("name", name=op.f("uq_lines_name")),
        schema="plant",
    )
    op.create_table(
        "steel_grades",
        sa.Column("id", sa.Uuid(), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column("code", sa.Text(), nullable=False),
        sa.Column("spec", sa.Text(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_steel_grades")),
        sa.UniqueConstraint("code", name=op.f("uq_steel_grades_code")),
        schema="plant",
    )
    op.create_table(
        "suppliers",
        sa.Column("id", sa.Uuid(), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column("name", sa.Text(), nullable=False),
        sa.Column("country", sa.String(length=2), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_suppliers")),
        sa.UniqueConstraint("name", name=op.f("uq_suppliers_name")),
        schema="plant",
    )
    op.create_table(
        "chunks",
        sa.Column("id", sa.Uuid(), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column("document_id", sa.Uuid(), nullable=False),
        sa.Column("ordinal", sa.Integer(), nullable=False),
        sa.Column("text", sa.Text(), nullable=False),
        sa.Column("context_header", sa.Text(), nullable=False),
        sa.Column("section_path", sa.Text(), nullable=False),
        sa.Column("page", sa.Integer(), nullable=True),
        sa.Column("language", sa.String(length=8), nullable=False),
        sa.Column("token_count", sa.Integer(), nullable=False),
        sa.Column("sha256", sa.String(length=64), nullable=False),
        sa.Column(
            "metadata",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default=sa.text("'{}'::jsonb"),
            nullable=False,
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["document_id"],
            ["kb.documents.id"],
            name=op.f("fk_chunks_document_id_documents"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_chunks")),
        sa.UniqueConstraint("document_id", "ordinal", name="uq_chunks_document_id_ordinal"),
        schema="kb",
    )
    op.create_index(op.f("ix_kb_chunks_sha256"), "chunks", ["sha256"], unique=False, schema="kb")
    op.create_table(
        "equipment",
        sa.Column("id", sa.Uuid(), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column("line_id", sa.Uuid(), nullable=False),
        sa.Column("tag", sa.Text(), nullable=False),
        sa.Column("type", sa.Text(), nullable=False),
        sa.Column("name", sa.Text(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["line_id"], ["plant.lines.id"], name=op.f("fk_equipment_line_id_lines")
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_equipment")),
        sa.UniqueConstraint("tag", name=op.f("uq_equipment_tag")),
        schema="plant",
    )
    op.create_index(
        op.f("ix_plant_equipment_line_id"), "equipment", ["line_id"], unique=False, schema="plant"
    )
    op.create_table(
        "incidents",
        sa.Column("id", sa.Uuid(), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column("title", sa.Text(), nullable=False),
        sa.Column("description", sa.Text(), nullable=False),
        sa.Column("line_id", sa.Uuid(), nullable=False),
        sa.Column("reported_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("severity", sa.SmallInteger(), nullable=False),
        sa.Column(
            "status",
            sa.Enum(
                "open",
                "investigating",
                "closed",
                name="incident_status",
                native_enum=False,
                create_constraint=False,
                length=32,
            ),
            server_default="open",
            nullable=False,
        ),
        sa.Column("language", sa.String(length=8), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.CheckConstraint(
            "status IN ('open', 'investigating', 'closed')",
            name=op.f("ck_incidents_incident_status"),
        ),
        sa.CheckConstraint("severity BETWEEN 1 AND 5", name=op.f("ck_incidents_severity_range")),
        sa.ForeignKeyConstraint(
            ["line_id"], ["plant.lines.id"], name=op.f("fk_incidents_line_id_lines")
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_incidents")),
        schema="plant",
    )
    op.create_index(
        "ix_incidents_line_id_reported_at",
        "incidents",
        ["line_id", "reported_at"],
        unique=False,
        schema="plant",
    )
    op.create_table(
        "material_lots",
        sa.Column("id", sa.Uuid(), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column("supplier_id", sa.Uuid(), nullable=False),
        sa.Column("grade_id", sa.Uuid(), nullable=False),
        sa.Column("received_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("cert_document_id", sa.Uuid(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["cert_document_id"],
            ["kb.documents.id"],
            name=op.f("fk_material_lots_cert_document_id_documents"),
        ),
        sa.ForeignKeyConstraint(
            ["grade_id"],
            ["plant.steel_grades.id"],
            name=op.f("fk_material_lots_grade_id_steel_grades"),
        ),
        sa.ForeignKeyConstraint(
            ["supplier_id"],
            ["plant.suppliers.id"],
            name=op.f("fk_material_lots_supplier_id_suppliers"),
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_material_lots")),
        schema="plant",
    )
    op.create_index(
        op.f("ix_plant_material_lots_cert_document_id"),
        "material_lots",
        ["cert_document_id"],
        unique=False,
        schema="plant",
    )
    op.create_index(
        op.f("ix_plant_material_lots_grade_id"),
        "material_lots",
        ["grade_id"],
        unique=False,
        schema="plant",
    )
    op.create_index(
        op.f("ix_plant_material_lots_received_at"),
        "material_lots",
        ["received_at"],
        unique=False,
        schema="plant",
    )
    op.create_index(
        op.f("ix_plant_material_lots_supplier_id"),
        "material_lots",
        ["supplier_id"],
        unique=False,
        schema="plant",
    )
    op.create_table(
        "investigations",
        sa.Column("id", sa.Uuid(), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column("incident_id", sa.Uuid(), nullable=False),
        sa.Column("created_by", sa.Uuid(), nullable=True),
        sa.Column(
            "status",
            sa.Enum(
                "running",
                "awaiting_review",
                "completed",
                "failed",
                name="investigation_status",
                native_enum=False,
                create_constraint=False,
                length=32,
            ),
            server_default="running",
            nullable=False,
        ),
        sa.Column("is_replay", sa.Boolean(), server_default=sa.text("false"), nullable=False),
        sa.Column(
            "config",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default=sa.text("'{}'::jsonb"),
            nullable=False,
        ),
        sa.Column(
            "started_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
        sa.CheckConstraint(
            "status IN ('running', 'awaiting_review', 'completed', 'failed')",
            name=op.f("ck_investigations_investigation_status"),
        ),
        sa.ForeignKeyConstraint(
            ["created_by"], ["app.users.id"], name=op.f("fk_investigations_created_by_users")
        ),
        sa.ForeignKeyConstraint(
            ["incident_id"],
            ["plant.incidents.id"],
            name=op.f("fk_investigations_incident_id_incidents"),
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_investigations")),
        schema="app",
    )
    op.create_index(
        op.f("ix_app_investigations_created_by"),
        "investigations",
        ["created_by"],
        unique=False,
        schema="app",
    )
    op.create_index(
        op.f("ix_app_investigations_incident_id"),
        "investigations",
        ["incident_id"],
        unique=False,
        schema="app",
    )
    op.create_index(
        op.f("ix_app_investigations_started_at"),
        "investigations",
        ["started_at"],
        unique=False,
        schema="app",
    )
    op.create_table(
        "injections",
        sa.Column("id", sa.Uuid(), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column("cause_id", sa.Uuid(), nullable=False),
        sa.Column("line_id", sa.Uuid(), nullable=False),
        sa.Column("equipment_id", sa.Uuid(), nullable=True),
        sa.Column("start_ts", sa.DateTime(timezone=True), nullable=False),
        sa.Column("end_ts", sa.DateTime(timezone=True), nullable=False),
        sa.Column(
            "params",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default=sa.text("'{}'::jsonb"),
            nullable=False,
        ),
        sa.CheckConstraint("end_ts > start_ts", name=op.f("ck_injections_window_order")),
        sa.ForeignKeyConstraint(
            ["cause_id"], ["eval.root_causes.id"], name=op.f("fk_injections_cause_id_root_causes")
        ),
        sa.ForeignKeyConstraint(
            ["equipment_id"],
            ["plant.equipment.id"],
            name=op.f("fk_injections_equipment_id_equipment"),
        ),
        sa.ForeignKeyConstraint(
            ["line_id"], ["plant.lines.id"], name=op.f("fk_injections_line_id_lines")
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_injections")),
        schema="eval",
    )
    op.create_index(
        op.f("ix_eval_injections_cause_id"), "injections", ["cause_id"], unique=False, schema="eval"
    )
    op.create_index(
        op.f("ix_eval_injections_equipment_id"),
        "injections",
        ["equipment_id"],
        unique=False,
        schema="eval",
    )
    op.create_index(
        "ix_injections_line_id_start_ts",
        "injections",
        ["line_id", "start_ts"],
        unique=False,
        schema="eval",
    )
    op.create_table(
        "questions",
        sa.Column("id", sa.Uuid(), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column(
            "kind",
            sa.Enum(
                "retrieval",
                "rca",
                "sql",
                "image",
                name="question_kind",
                native_enum=False,
                create_constraint=False,
                length=32,
            ),
            nullable=False,
        ),
        sa.Column("query", sa.Text(), nullable=False),
        sa.Column("incident_id", sa.Uuid(), nullable=True),
        sa.Column(
            "gold_chunk_ids",
            postgresql.ARRAY(sa.Uuid()),
            server_default=sa.text("'{}'::uuid[]"),
            nullable=False,
        ),
        sa.Column("gold_cause_id", sa.Uuid(), nullable=True),
        sa.Column("gold_answer", sa.Text(), nullable=True),
        sa.CheckConstraint(
            "kind IN ('retrieval', 'rca', 'sql', 'image')", name=op.f("ck_questions_question_kind")
        ),
        sa.ForeignKeyConstraint(
            ["gold_cause_id"],
            ["eval.root_causes.id"],
            name=op.f("fk_questions_gold_cause_id_root_causes"),
        ),
        sa.ForeignKeyConstraint(
            ["incident_id"], ["plant.incidents.id"], name=op.f("fk_questions_incident_id_incidents")
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_questions")),
        schema="eval",
    )
    op.create_index(
        op.f("ix_eval_questions_gold_cause_id"),
        "questions",
        ["gold_cause_id"],
        unique=False,
        schema="eval",
    )
    op.create_index(
        op.f("ix_eval_questions_incident_id"),
        "questions",
        ["incident_id"],
        unique=False,
        schema="eval",
    )
    op.create_table(
        "coils",
        sa.Column("id", sa.Uuid(), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column("line_id", sa.Uuid(), nullable=False),
        sa.Column("lot_id", sa.Uuid(), nullable=False),
        sa.Column("grade_id", sa.Uuid(), nullable=False),
        sa.Column("shift", sa.Text(), nullable=False),
        sa.Column("crew", sa.Text(), nullable=False),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["grade_id"], ["plant.steel_grades.id"], name=op.f("fk_coils_grade_id_steel_grades")
        ),
        sa.ForeignKeyConstraint(
            ["line_id"], ["plant.lines.id"], name=op.f("fk_coils_line_id_lines")
        ),
        sa.ForeignKeyConstraint(
            ["lot_id"], ["plant.material_lots.id"], name=op.f("fk_coils_lot_id_material_lots")
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_coils")),
        schema="plant",
    )
    op.create_index(
        "ix_coils_line_id_started_at",
        "coils",
        ["line_id", "started_at"],
        unique=False,
        schema="plant",
    )
    op.create_index(
        op.f("ix_plant_coils_grade_id"), "coils", ["grade_id"], unique=False, schema="plant"
    )
    op.create_index(
        op.f("ix_plant_coils_lot_id"), "coils", ["lot_id"], unique=False, schema="plant"
    )
    op.create_table(
        "maintenance_events",
        sa.Column("id", sa.Uuid(), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column("equipment_id", sa.Uuid(), nullable=False),
        sa.Column("ts", sa.DateTime(timezone=True), nullable=False),
        sa.Column(
            "kind",
            sa.Enum(
                "planned",
                "unplanned",
                name="maintenance_kind",
                native_enum=False,
                create_constraint=False,
                length=32,
            ),
            nullable=False,
        ),
        sa.Column("description", sa.Text(), nullable=False),
        sa.Column("technician", sa.Text(), nullable=False),
        sa.CheckConstraint(
            "kind IN ('planned', 'unplanned')", name=op.f("ck_maintenance_events_maintenance_kind")
        ),
        sa.ForeignKeyConstraint(
            ["equipment_id"],
            ["plant.equipment.id"],
            name=op.f("fk_maintenance_events_equipment_id_equipment"),
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_maintenance_events")),
        schema="plant",
    )
    op.create_index(
        "ix_maintenance_events_equipment_id_ts",
        "maintenance_events",
        ["equipment_id", "ts"],
        unique=False,
        schema="plant",
    )
    op.create_table(
        "process_readings",
        sa.Column("id", sa.BigInteger(), sa.Identity(always=True), nullable=False),
        sa.Column("line_id", sa.Uuid(), nullable=False),
        sa.Column("equipment_id", sa.Uuid(), nullable=False),
        sa.Column("ts", sa.DateTime(timezone=True), nullable=False),
        sa.Column("parameter", sa.Text(), nullable=False),
        sa.Column("value", sa.Double(), nullable=False),
        sa.Column("unit", sa.Text(), nullable=False),
        sa.ForeignKeyConstraint(
            ["equipment_id"],
            ["plant.equipment.id"],
            name=op.f("fk_process_readings_equipment_id_equipment"),
        ),
        sa.ForeignKeyConstraint(
            ["line_id"], ["plant.lines.id"], name=op.f("fk_process_readings_line_id_lines")
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_process_readings")),
        schema="plant",
    )
    op.create_index(
        "ix_process_readings_equipment_parameter_ts",
        "process_readings",
        ["equipment_id", "parameter", "ts"],
        unique=False,
        schema="plant",
    )
    op.create_index(
        "ix_process_readings_line_id_ts",
        "process_readings",
        ["line_id", "ts"],
        unique=False,
        schema="plant",
    )
    op.create_table(
        "evidence",
        sa.Column("id", sa.Uuid(), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column("investigation_id", sa.Uuid(), nullable=False),
        sa.Column(
            "source_type",
            sa.Enum(
                "chunk",
                "image",
                "sql",
                "defect",
                name="evidence_source_type",
                native_enum=False,
                create_constraint=False,
                length=32,
            ),
            nullable=False,
        ),
        sa.Column("source_id", sa.Text(), nullable=False),
        sa.Column("snapshot", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("retrieval_score", sa.Double(), nullable=True),
        sa.Column("rerank_score", sa.Double(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.CheckConstraint(
            "source_type IN ('chunk', 'image', 'sql', 'defect')",
            name=op.f("ck_evidence_evidence_source_type"),
        ),
        sa.ForeignKeyConstraint(
            ["investigation_id"],
            ["app.investigations.id"],
            name=op.f("fk_evidence_investigation_id_investigations"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_evidence")),
        schema="app",
    )
    op.create_index(
        op.f("ix_app_evidence_investigation_id"),
        "evidence",
        ["investigation_id"],
        unique=False,
        schema="app",
    )
    op.create_table(
        "hypotheses",
        sa.Column("id", sa.Uuid(), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column("investigation_id", sa.Uuid(), nullable=False),
        sa.Column(
            "category_6m",
            sa.Enum(
                "man",
                "machine",
                "method",
                "material",
                "measurement",
                "environment",
                name="category_6m",
                native_enum=False,
                create_constraint=False,
                length=32,
            ),
            nullable=False,
        ),
        sa.Column("statement", sa.Text(), nullable=False),
        sa.Column("confidence", sa.Double(), nullable=False),
        sa.Column(
            "status",
            sa.Enum(
                "proposed",
                "accepted",
                "rejected",
                name="hypothesis_status",
                native_enum=False,
                create_constraint=False,
                length=32,
            ),
            server_default="proposed",
            nullable=False,
        ),
        sa.Column("reviewer_note", sa.Text(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.CheckConstraint(
            "category_6m IN ('man', 'machine', 'method', 'material', 'measurement', 'environment')",
            name=op.f("ck_hypotheses_category_6m"),
        ),
        sa.CheckConstraint(
            "status IN ('proposed', 'accepted', 'rejected')",
            name=op.f("ck_hypotheses_hypothesis_status"),
        ),
        sa.CheckConstraint(
            "confidence BETWEEN 0 AND 1", name=op.f("ck_hypotheses_confidence_range")
        ),
        sa.ForeignKeyConstraint(
            ["investigation_id"],
            ["app.investigations.id"],
            name=op.f("fk_hypotheses_investigation_id_investigations"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_hypotheses")),
        schema="app",
    )
    op.create_index(
        op.f("ix_app_hypotheses_investigation_id"),
        "hypotheses",
        ["investigation_id"],
        unique=False,
        schema="app",
    )
    op.create_table(
        "reports",
        sa.Column("id", sa.Uuid(), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column("investigation_id", sa.Uuid(), nullable=False),
        sa.Column("markdown", sa.Text(), nullable=False),
        sa.Column("grounding_score", sa.Double(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["investigation_id"],
            ["app.investigations.id"],
            name=op.f("fk_reports_investigation_id_investigations"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_reports")),
        schema="app",
    )
    op.create_index(
        op.f("ix_app_reports_investigation_id"),
        "reports",
        ["investigation_id"],
        unique=False,
        schema="app",
    )
    op.create_table(
        "steps",
        sa.Column("id", sa.Uuid(), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column("investigation_id", sa.Uuid(), nullable=False),
        sa.Column("step_no", sa.Integer(), nullable=False),
        sa.Column("node", sa.Text(), nullable=False),
        sa.Column("tool", sa.Text(), nullable=True),
        sa.Column(
            "input",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default=sa.text("'{}'::jsonb"),
            nullable=False,
        ),
        sa.Column("output_summary", sa.Text(), nullable=True),
        sa.Column("latency_ms", sa.Integer(), nullable=True),
        sa.Column("tokens_in", sa.Integer(), nullable=True),
        sa.Column("tokens_out", sa.Integer(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["investigation_id"],
            ["app.investigations.id"],
            name=op.f("fk_steps_investigation_id_investigations"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_steps")),
        sa.UniqueConstraint("investigation_id", "step_no", name="uq_steps_investigation_step"),
        schema="app",
    )
    op.create_table(
        "results",
        sa.Column("run_id", sa.Uuid(), nullable=False),
        sa.Column("question_id", sa.Uuid(), nullable=False),
        sa.Column("metric", sa.Text(), nullable=False),
        sa.Column("value", sa.Double(), nullable=False),
        sa.ForeignKeyConstraint(
            ["question_id"], ["eval.questions.id"], name=op.f("fk_results_question_id_questions")
        ),
        sa.ForeignKeyConstraint(
            ["run_id"], ["eval.runs.id"], name=op.f("fk_results_run_id_runs"), ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("run_id", "question_id", "metric", name=op.f("pk_results")),
        schema="eval",
    )
    op.create_index(
        op.f("ix_eval_results_question_id"), "results", ["question_id"], unique=False, schema="eval"
    )
    op.create_table(
        "inspections",
        sa.Column("id", sa.Uuid(), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column("coil_id", sa.Uuid(), nullable=False),
        sa.Column("ts", sa.DateTime(timezone=True), nullable=False),
        sa.Column("method", sa.Text(), nullable=False),
        sa.Column("result", sa.Text(), nullable=False),
        sa.ForeignKeyConstraint(
            ["coil_id"], ["plant.coils.id"], name=op.f("fk_inspections_coil_id_coils")
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_inspections")),
        schema="plant",
    )
    op.create_index(
        op.f("ix_plant_inspections_coil_id"),
        "inspections",
        ["coil_id"],
        unique=False,
        schema="plant",
    )
    op.create_index(
        op.f("ix_plant_inspections_ts"), "inspections", ["ts"], unique=False, schema="plant"
    )
    op.create_table(
        "hypothesis_evidence",
        sa.Column("hypothesis_id", sa.Uuid(), nullable=False),
        sa.Column("evidence_id", sa.Uuid(), nullable=False),
        sa.Column(
            "stance",
            sa.Enum(
                "supports",
                "contradicts",
                name="stance",
                native_enum=False,
                create_constraint=False,
                length=32,
            ),
            nullable=False,
        ),
        sa.CheckConstraint(
            "stance IN ('supports', 'contradicts')", name=op.f("ck_hypothesis_evidence_stance")
        ),
        sa.ForeignKeyConstraint(
            ["evidence_id"],
            ["app.evidence.id"],
            name=op.f("fk_hypothesis_evidence_evidence_id_evidence"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["hypothesis_id"],
            ["app.hypotheses.id"],
            name=op.f("fk_hypothesis_evidence_hypothesis_id_hypotheses"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint(
            "hypothesis_id", "evidence_id", name=op.f("pk_hypothesis_evidence")
        ),
        schema="app",
    )
    op.create_index(
        op.f("ix_app_hypothesis_evidence_evidence_id"),
        "hypothesis_evidence",
        ["evidence_id"],
        unique=False,
        schema="app",
    )
    op.create_table(
        "defects",
        sa.Column("id", sa.Uuid(), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column("inspection_id", sa.Uuid(), nullable=False),
        sa.Column("coil_id", sa.Uuid(), nullable=False),
        sa.Column("defect_class", sa.Text(), nullable=False),
        sa.Column("severity", sa.SmallInteger(), nullable=False),
        sa.Column("position_m", sa.Double(), nullable=False),
        sa.Column("image_id", sa.Uuid(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.CheckConstraint("severity BETWEEN 1 AND 5", name=op.f("ck_defects_severity_range")),
        sa.ForeignKeyConstraint(
            ["coil_id"], ["plant.coils.id"], name=op.f("fk_defects_coil_id_coils")
        ),
        sa.ForeignKeyConstraint(
            ["image_id"], ["kb.images.id"], name=op.f("fk_defects_image_id_images")
        ),
        sa.ForeignKeyConstraint(
            ["inspection_id"],
            ["plant.inspections.id"],
            name=op.f("fk_defects_inspection_id_inspections"),
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_defects")),
        schema="plant",
    )
    op.create_index(
        op.f("ix_plant_defects_coil_id"), "defects", ["coil_id"], unique=False, schema="plant"
    )
    op.create_index(
        op.f("ix_plant_defects_defect_class"),
        "defects",
        ["defect_class"],
        unique=False,
        schema="plant",
    )
    op.create_index(
        op.f("ix_plant_defects_image_id"), "defects", ["image_id"], unique=False, schema="plant"
    )
    op.create_index(
        op.f("ix_plant_defects_inspection_id"),
        "defects",
        ["inspection_id"],
        unique=False,
        schema="plant",
    )

    op.execute(coil_process_summary_sql())
    # Unique index enables REFRESH MATERIALIZED VIEW CONCURRENTLY.
    op.execute(
        "CREATE UNIQUE INDEX ux_coil_process_summary_coil_id ON plant.coil_process_summary (coil_id)"
    )


def downgrade() -> None:
    # Schemas are kept: they carry the role grants from roles.sql.
    op.execute("DROP MATERIALIZED VIEW IF EXISTS plant.coil_process_summary")
    op.drop_index(op.f("ix_plant_defects_inspection_id"), table_name="defects", schema="plant")
    op.drop_index(op.f("ix_plant_defects_image_id"), table_name="defects", schema="plant")
    op.drop_index(op.f("ix_plant_defects_defect_class"), table_name="defects", schema="plant")
    op.drop_index(op.f("ix_plant_defects_coil_id"), table_name="defects", schema="plant")
    op.drop_table("defects", schema="plant")
    op.drop_index(
        op.f("ix_app_hypothesis_evidence_evidence_id"),
        table_name="hypothesis_evidence",
        schema="app",
    )
    op.drop_table("hypothesis_evidence", schema="app")
    op.drop_index(op.f("ix_plant_inspections_ts"), table_name="inspections", schema="plant")
    op.drop_index(op.f("ix_plant_inspections_coil_id"), table_name="inspections", schema="plant")
    op.drop_table("inspections", schema="plant")
    op.drop_index(op.f("ix_eval_results_question_id"), table_name="results", schema="eval")
    op.drop_table("results", schema="eval")
    op.drop_table("steps", schema="app")
    op.drop_index(op.f("ix_app_reports_investigation_id"), table_name="reports", schema="app")
    op.drop_table("reports", schema="app")
    op.drop_index(op.f("ix_app_hypotheses_investigation_id"), table_name="hypotheses", schema="app")
    op.drop_table("hypotheses", schema="app")
    op.drop_index(op.f("ix_app_evidence_investigation_id"), table_name="evidence", schema="app")
    op.drop_table("evidence", schema="app")
    op.drop_index("ix_process_readings_line_id_ts", table_name="process_readings", schema="plant")
    op.drop_index(
        "ix_process_readings_equipment_parameter_ts", table_name="process_readings", schema="plant"
    )
    op.drop_table("process_readings", schema="plant")
    op.drop_index(
        "ix_maintenance_events_equipment_id_ts", table_name="maintenance_events", schema="plant"
    )
    op.drop_table("maintenance_events", schema="plant")
    op.drop_index(op.f("ix_plant_coils_lot_id"), table_name="coils", schema="plant")
    op.drop_index(op.f("ix_plant_coils_grade_id"), table_name="coils", schema="plant")
    op.drop_index("ix_coils_line_id_started_at", table_name="coils", schema="plant")
    op.drop_table("coils", schema="plant")
    op.drop_index(op.f("ix_eval_questions_incident_id"), table_name="questions", schema="eval")
    op.drop_index(op.f("ix_eval_questions_gold_cause_id"), table_name="questions", schema="eval")
    op.drop_table("questions", schema="eval")
    op.drop_index("ix_injections_line_id_start_ts", table_name="injections", schema="eval")
    op.drop_index(op.f("ix_eval_injections_equipment_id"), table_name="injections", schema="eval")
    op.drop_index(op.f("ix_eval_injections_cause_id"), table_name="injections", schema="eval")
    op.drop_table("injections", schema="eval")
    op.drop_index(
        op.f("ix_app_investigations_started_at"), table_name="investigations", schema="app"
    )
    op.drop_index(
        op.f("ix_app_investigations_incident_id"), table_name="investigations", schema="app"
    )
    op.drop_index(
        op.f("ix_app_investigations_created_by"), table_name="investigations", schema="app"
    )
    op.drop_table("investigations", schema="app")
    op.drop_index(
        op.f("ix_plant_material_lots_supplier_id"), table_name="material_lots", schema="plant"
    )
    op.drop_index(
        op.f("ix_plant_material_lots_received_at"), table_name="material_lots", schema="plant"
    )
    op.drop_index(
        op.f("ix_plant_material_lots_grade_id"), table_name="material_lots", schema="plant"
    )
    op.drop_index(
        op.f("ix_plant_material_lots_cert_document_id"), table_name="material_lots", schema="plant"
    )
    op.drop_table("material_lots", schema="plant")
    op.drop_index("ix_incidents_line_id_reported_at", table_name="incidents", schema="plant")
    op.drop_table("incidents", schema="plant")
    op.drop_index(op.f("ix_plant_equipment_line_id"), table_name="equipment", schema="plant")
    op.drop_table("equipment", schema="plant")
    op.drop_index(op.f("ix_kb_chunks_sha256"), table_name="chunks", schema="kb")
    op.drop_table("chunks", schema="kb")
    op.drop_table("suppliers", schema="plant")
    op.drop_table("steel_grades", schema="plant")
    op.drop_table("lines", schema="plant")
    op.drop_table("index_state", schema="kb")
    op.drop_table("images", schema="kb")
    op.drop_index(op.f("ix_kb_documents_doc_type"), table_name="documents", schema="kb")
    op.drop_index("ix_documents_effective", table_name="documents", schema="kb")
    op.drop_table("documents", schema="kb")
    op.drop_index(op.f("ix_eval_runs_started_at"), table_name="runs", schema="eval")
    op.drop_table("runs", schema="eval")
    op.drop_table("root_causes", schema="eval")
    op.drop_table("users", schema="app")
    op.drop_table("quota_usage", schema="app")
    op.drop_table("llm_cache", schema="app")
