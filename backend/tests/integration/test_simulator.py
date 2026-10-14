from collections.abc import Iterator
from pathlib import Path
from typing import LiteralString, cast

import psycopg
import pytest
from psycopg import errors

from simulator import SimConfig, SimulatorError, Summary, generate, simulate
from simulator.model import Dataset
from simulator.writer import reset_tables
from ursache.config import Settings
from ursache.db import admin

pytestmark = pytest.mark.integration

CONFIG = SimConfig(seed=7, days=21, coils_per_day=12, samples_per_coil=1)


def connect(url: str) -> psycopg.Connection:
    return psycopg.connect(admin.libpq_url(url), autocommit=True)


def scalar(conn: psycopg.Connection, query: LiteralString) -> object:
    row = conn.execute(query).fetchone()
    assert row is not None
    return row[0]


@pytest.fixture(scope="module")
def docs_dir(tmp_path_factory: pytest.TempPathFactory) -> Path:
    return tmp_path_factory.mktemp("docs")


@pytest.fixture(scope="module")
def simulated(settings: Settings, docs_dir: Path) -> Iterator[tuple[Summary, Dataset]]:
    url = admin.libpq_url(settings.migration_database_url)
    summary = simulate(CONFIG, url, docs_dir, reset=True)
    yield summary, generate(CONFIG)
    with psycopg.connect(url) as conn:
        reset_tables(conn)


def test_row_counts_are_in_expected_ranges(
    settings: Settings, simulated: tuple[Summary, Dataset]
) -> None:
    summary, _ = simulated
    expected: dict[LiteralString, tuple[int, int]] = {
        "plant.lines": (2, 2),
        "plant.equipment": (22, 22),
        "plant.suppliers": (4, 4),
        "plant.steel_grades": (5, 5),
        "plant.material_lots": (20, 120),
        "plant.coils": (504, 504),
        "plant.process_readings": (504 * 23, 504 * 23),
        "plant.inspections": (504, 504),
        "plant.defects": (50, 600),
        "plant.maintenance_events": (60, 250),
        "plant.incidents": (12, 12),
        "kb.documents": (40, 140),
        "eval.root_causes": (6, 6),
        "eval.injections": (6, 6),
        "eval.questions": (20, 30),
    }
    with connect(settings.migration_database_url) as conn:
        for table, (low, high) in expected.items():
            count = scalar(conn, f"SELECT count(*) FROM {table}")
            assert isinstance(count, int)
            assert low <= count <= high, (table, count)
    assert summary.size_mb > 0


def test_coil_summary_has_one_row_per_coil(
    settings: Settings, simulated: tuple[Summary, Dataset]
) -> None:
    with connect(settings.agent_database_url) as conn:
        rows = scalar(conn, "SELECT count(*) FROM plant.coil_process_summary")
        distinct = scalar(conn, "SELECT count(DISTINCT coil_id) FROM plant.coil_process_summary")
        coils = scalar(conn, "SELECT count(*) FROM plant.coils")
        unread = scalar(
            conn, "SELECT count(*) FROM plant.coil_process_summary WHERE roll_force_mean IS NULL"
        )
    assert rows == distinct == coils
    assert unread == 0


def test_agent_reads_plant_and_kb_but_not_eval(
    settings: Settings, simulated: tuple[Summary, Dataset]
) -> None:
    with connect(settings.agent_database_url) as conn:
        assert scalar(conn, "SELECT count(*) FROM plant.incidents") == 12
        assert scalar(conn, "SELECT count(*) FROM kb.documents") != 0
        for table in ("eval.root_causes", "eval.injections", "eval.questions"):
            with pytest.raises(errors.InsufficientPrivilege):
                conn.execute(f"SELECT * FROM {table}")


def test_sql_gold_answers_match_the_database(
    settings: Settings, simulated: tuple[Summary, Dataset]
) -> None:
    _, dataset = simulated
    with connect(settings.agent_database_url) as conn:
        for question in dataset.questions:
            if question.kind != "sql":
                continue
            assert question.check_sql and question.gold_answer
            actual = scalar(conn, cast(LiteralString, question.check_sql))
            assert str(actual) == question.gold_answer, question.query


def test_plant_and_kb_text_hold_no_ground_truth_ids(
    settings: Settings, simulated: tuple[Summary, Dataset]
) -> None:
    with connect(settings.eval_database_url) as conn:
        secrets = [
            str(r[0])
            for r in conn.execute(
                "SELECT id FROM eval.injections UNION ALL SELECT id FROM eval.root_causes"
            )
        ]
        haystack = scalar(
            conn,
            "SELECT string_agg(t, ' ') FROM ("
            " SELECT title || description AS t FROM plant.incidents"
            " UNION ALL SELECT description FROM plant.maintenance_events"
            " UNION ALL SELECT title || source_path FROM kb.documents) s",
        )
    assert isinstance(haystack, str)
    assert not [s for s in secrets if s in haystack]


def test_rerun_needs_reset_and_reset_reproduces_the_data(
    settings: Settings, simulated: tuple[Summary, Dataset], docs_dir: Path
) -> None:
    summary, _ = simulated
    url = admin.libpq_url(settings.migration_database_url)
    with pytest.raises(SimulatorError, match="--reset"):
        simulate(CONFIG, url, docs_dir, reset=False)

    again = simulate(CONFIG, url, docs_dir, reset=True)
    assert again.digest == summary.digest
    assert again.counts == summary.counts
    files = list(docs_dir.rglob("*.md"))
    assert len(files) == summary.counts["documents"]
