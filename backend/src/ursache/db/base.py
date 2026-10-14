from __future__ import annotations

import enum
import uuid
from datetime import datetime

import sqlalchemy as sa
from sqlalchemy.orm import DeclarativeBase, MappedColumn, mapped_column

SCHEMAS = ("plant", "kb", "app", "eval")

NAMING_CONVENTION = {
    "ix": "ix_%(column_0_label)s",
    "uq": "uq_%(table_name)s_%(column_0_name)s",
    "ck": "ck_%(table_name)s_%(constraint_name)s",
    "fk": "fk_%(table_name)s_%(column_0_name)s_%(referred_table_name)s",
    "pk": "pk_%(table_name)s",
}


class Base(DeclarativeBase):
    metadata = sa.MetaData(naming_convention=NAMING_CONVENTION)


def uuid_pk() -> MappedColumn[uuid.UUID]:
    return mapped_column(
        sa.Uuid, primary_key=True, default=uuid.uuid4, server_default=sa.text("gen_random_uuid()")
    )


def created_at() -> MappedColumn[datetime]:
    return mapped_column(sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False)


def str_enum(enum_cls: type[enum.StrEnum], name: str) -> sa.Enum:
    """VARCHAR + CHECK constraint; avoids ALTER TYPE pain when a closed set grows."""
    return sa.Enum(
        enum_cls,
        name=name,
        native_enum=False,
        create_constraint=True,
        length=32,
        values_callable=_enum_values,
    )


def _enum_values(enum_cls: type[enum.StrEnum]) -> list[str]:
    return [member.value for member in enum_cls]
