from __future__ import annotations

import asyncio

from alembic import context
from sqlalchemy.engine import Connection
from sqlalchemy.ext.asyncio import create_async_engine

from ursache.config import get_settings
from ursache.db.base import SCHEMAS
from ursache.db.models import metadata

config = context.config
target_metadata = metadata


def _url() -> str:
    return config.get_main_option("sqlalchemy.url") or get_settings().migration_database_url


def _include_name(name: str | None, type_: str, _parent: object) -> bool:
    if type_ == "schema":
        return name in SCHEMAS
    return True


def _configure(connection: Connection | None = None) -> None:
    context.configure(
        connection=connection,
        url=None if connection else _url(),
        target_metadata=target_metadata,
        include_schemas=True,
        include_name=_include_name,
        compare_type=True,
        literal_binds=connection is None,
    )


def run_migrations_offline() -> None:
    _configure()
    with context.begin_transaction():
        context.run_migrations()


def _run_sync(connection: Connection) -> None:
    _configure(connection)
    with context.begin_transaction():
        context.run_migrations()


async def run_migrations_online() -> None:
    engine = create_async_engine(_url())
    async with engine.connect() as connection:
        await connection.run_sync(_run_sync)
    await engine.dispose()


if context.is_offline_mode():
    run_migrations_offline()
else:
    asyncio.run(run_migrations_online())
