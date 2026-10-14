import psycopg
import pytest
from psycopg import errors

from ursache.config import Settings
from ursache.db import admin

pytestmark = pytest.mark.integration


def connect(url: str) -> psycopg.Connection:
    return psycopg.connect(admin.libpq_url(url), autocommit=True)


def test_downgrade_to_base_and_upgrade_to_head(settings: Settings) -> None:
    admin.downgrade(settings, "base")
    with connect(settings.migration_database_url) as conn:
        remaining = conn.execute(
            "SELECT count(*) FROM pg_tables WHERE schemaname IN ('plant','kb','app','eval')"
        ).fetchone()
        assert remaining == (0,)

    admin.upgrade(settings, "head")
    with connect(settings.migration_database_url) as conn:
        tables = conn.execute(
            "SELECT schemaname, count(*) FROM pg_tables"
            " WHERE schemaname IN ('plant','kb','app','eval') GROUP BY schemaname"
        ).fetchall()
        views = conn.execute("SELECT matviewname FROM pg_matviews").fetchall()
    assert dict(tables) == {"plant": 11, "kb": 4, "app": 9, "eval": 5}
    assert views == [("coil_process_summary",)]


def test_agent_cannot_read_eval(settings: Settings) -> None:
    with connect(settings.agent_database_url) as conn, pytest.raises(errors.InsufficientPrivilege):
        conn.execute("SELECT * FROM eval.root_causes")


def test_agent_cannot_write_plant(settings: Settings) -> None:
    with (
        connect(settings.agent_database_url) as conn,
        pytest.raises((errors.InsufficientPrivilege, errors.ReadOnlySqlTransaction)),
    ):
        conn.execute(
            "INSERT INTO plant.coils (line_id, lot_id, grade_id, shift, crew, started_at)"
            " VALUES (gen_random_uuid(), gen_random_uuid(), gen_random_uuid(), 'A', 'C1', now())"
        )


def test_agent_can_read_plant_and_kb_with_timeout(settings: Settings) -> None:
    with connect(settings.agent_database_url) as conn:
        conn.execute("SELECT count(*) FROM plant.coils")
        conn.execute("SELECT count(*) FROM kb.chunks")
        conn.execute("SELECT count(*) FROM plant.coil_process_summary")
        assert conn.execute("SHOW statement_timeout").fetchone() == ("5s",)


def test_agent_cannot_read_app(settings: Settings) -> None:
    with connect(settings.agent_database_url) as conn, pytest.raises(errors.InsufficientPrivilege):
        conn.execute("SELECT * FROM app.llm_cache")


def test_app_cannot_read_eval(settings: Settings) -> None:
    with connect(settings.app_database_url) as conn, pytest.raises(errors.InsufficientPrivilege):
        conn.execute("SELECT * FROM eval.questions")


def test_app_can_write_app_schema(settings: Settings) -> None:
    with connect(settings.app_database_url) as conn:
        conn.execute("INSERT INTO app.users (name, role) VALUES ('Role Test', 'engineer')")
        conn.execute("DELETE FROM app.users WHERE name = 'Role Test'")


def test_eval_role_reads_every_schema(settings: Settings) -> None:
    with connect(settings.eval_database_url) as conn:
        for table in ("plant.coils", "kb.chunks", "app.investigations", "eval.root_causes"):
            conn.execute(f"SELECT count(*) FROM {table}")


async def test_seed_is_idempotent(settings: Settings) -> None:
    first = await admin.seed_users(settings)
    second = await admin.seed_users(settings)
    assert (first, second) == (3, 0)
