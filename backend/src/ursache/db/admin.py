"""Operational database tasks shared by the CLI and the integration tests."""

from __future__ import annotations

import logging
from pathlib import Path

import psycopg
from alembic import command
from alembic.config import Config
from psycopg import sql
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.engine import make_url

from ursache.config import Settings
from ursache.db.models.app import User, UserRole
from ursache.db.session import make_engine

logger = logging.getLogger(__name__)

MIGRATIONS_DIR = Path(__file__).resolve().parent.parent / "migrations"
ROLES_SQL = MIGRATIONS_DIR / "roles.sql"
EXPECTED_ROLES = {
    "app_database_url": "ursache_app",
    "agent_database_url": "ursache_agent",
    "eval_database_url": "ursache_eval",
}

SEED_USERS: tuple[tuple[str, UserRole], ...] = (
    ("Erika Engineer", UserRole.ENGINEER),
    ("Max Manager", UserRole.MANAGER),
    ("Ada Admin", UserRole.ADMIN),
)

__all__ = ["apply_roles", "downgrade", "libpq_url", "seed_users", "upgrade"]


def libpq_url(sqlalchemy_url: str) -> str:
    """Strip the SQLAlchemy driver suffix so psycopg can connect directly."""
    return (
        make_url(sqlalchemy_url).set(drivername="postgresql").render_as_string(hide_password=False)
    )


def alembic_config(settings: Settings) -> Config:
    cfg = Config()
    cfg.set_main_option("script_location", str(MIGRATIONS_DIR))
    cfg.set_main_option(
        "sqlalchemy.url",
        settings.migration_database_url.replace("%", "%%"),
    )
    return cfg


def upgrade(settings: Settings, revision: str = "head") -> None:
    command.upgrade(alembic_config(settings), revision)


def downgrade(settings: Settings, revision: str = "base") -> None:
    command.downgrade(alembic_config(settings), revision)


def apply_roles(settings: Settings) -> None:
    """Create schemas, roles and grants, then set each role's password from its URL."""
    with psycopg.connect(libpq_url(settings.migration_database_url), autocommit=True) as conn:
        conn.execute(ROLES_SQL.read_text(encoding="utf-8").encode())
        for field, role in EXPECTED_ROLES.items():
            url = make_url(getattr(settings, field))
            if url.username != role:
                raise ValueError(f"{field.upper()} must connect as {role!r}, got {url.username!r}")
            if url.password:
                conn.execute(
                    sql.SQL("ALTER ROLE {} WITH LOGIN PASSWORD {}").format(
                        sql.Identifier(role), sql.Literal(str(url.password))
                    )
                )
    logger.info("roles applied", extra={"roles": sorted(EXPECTED_ROLES.values())})


async def seed_users(settings: Settings) -> int:
    """Insert one user per role; idempotent. Runs as the app role."""
    engine = make_engine(settings.app_database_url, pool_size=1)
    try:
        async with engine.begin() as conn:
            stmt = (
                pg_insert(User)
                .values([{"name": name, "role": role} for name, role in SEED_USERS])
                .on_conflict_do_nothing(index_elements=[User.name])
                .returning(User.id)
            )
            return len((await conn.execute(stmt)).all())
    finally:
        await engine.dispose()
