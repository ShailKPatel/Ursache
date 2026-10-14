"""Integration fixtures. Requires the Compose services (or CI service containers).

Tests run against a throwaway database and `test_`-prefixed Qdrant collections, so the
developer's dev data is never touched.
"""

from collections.abc import AsyncIterator, Iterator

import psycopg
import pytest
from psycopg import sql
from qdrant_client import AsyncQdrantClient
from sqlalchemy.engine import make_url

from ursache.config import Settings
from ursache.db import admin
from ursache.indexing.qdrant_bootstrap import make_qdrant_client

TEST_DB = "ursache_test"


def _with_db(url: str, database: str) -> str:
    return make_url(url).set(database=database).render_as_string(hide_password=False)


@pytest.fixture(scope="session")
def settings() -> Iterator[Settings]:
    base = Settings()
    maintenance_url = admin.libpq_url(base.migration_database_url)
    try:
        conn = psycopg.connect(maintenance_url, autocommit=True, connect_timeout=5)
    except psycopg.OperationalError as exc:
        pytest.exit(f"Postgres not reachable ({exc}); start it with `make up`", returncode=2)
    with conn:
        conn.execute(
            sql.SQL("DROP DATABASE IF EXISTS {} WITH (FORCE)").format(sql.Identifier(TEST_DB))
        )
        conn.execute(sql.SQL("CREATE DATABASE {}").format(sql.Identifier(TEST_DB)))

    settings = base.model_copy(
        update={
            "migration_database_url": _with_db(base.migration_database_url, TEST_DB),
            "app_database_url": _with_db(base.app_database_url, TEST_DB),
            "agent_database_url": _with_db(base.agent_database_url, TEST_DB),
            "eval_database_url": _with_db(base.eval_database_url, TEST_DB),
            "qdrant_doc_chunks_collection": "test_" + base.qdrant_doc_chunks_collection,
            "qdrant_doc_chunks_alias": "test_" + base.qdrant_doc_chunks_alias,
            "qdrant_defect_images_collection": "test_" + base.qdrant_defect_images_collection,
            "qdrant_defect_images_alias": "test_" + base.qdrant_defect_images_alias,
        }
    )
    admin.apply_roles(settings)
    admin.upgrade(settings)
    yield settings

    with psycopg.connect(maintenance_url, autocommit=True) as conn:
        conn.execute(
            sql.SQL("DROP DATABASE IF EXISTS {} WITH (FORCE)").format(sql.Identifier(TEST_DB))
        )


@pytest.fixture
async def qdrant(settings: Settings) -> AsyncIterator[AsyncQdrantClient]:
    client = make_qdrant_client(settings)
    try:
        yield client
    finally:
        for name in (
            settings.qdrant_doc_chunks_collection,
            settings.qdrant_defect_images_collection,
        ):
            await client.delete_collection(name)
        await client.close()
