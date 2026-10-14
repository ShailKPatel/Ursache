from collections import Counter

import pytest
from fastapi.testclient import TestClient
from qdrant_client import AsyncQdrantClient
from sqlalchemy.ext.asyncio import async_sessionmaker

from tests.fakes import FakeLLMClient
from ursache.api.main import create_app
from ursache.config import Settings
from ursache.db.session import make_engine
from ursache.indexing.qdrant_bootstrap import bootstrap, collection_specs
from ursache.llm.cache import CachedLLMClient, PostgresCacheStore
from ursache.llm.quota import PostgresQuotaStore, QuotaExceeded, QuotaGuard

pytestmark = pytest.mark.integration


async def test_qdrant_bootstrap_is_idempotent(
    settings: Settings, qdrant: AsyncQdrantClient
) -> None:
    first = await bootstrap(settings, qdrant)
    second = await bootstrap(settings, qdrant)

    specs = collection_specs(settings)
    assert sorted(first) == sorted(s.name for s in specs)
    assert second == []

    aliases = (await qdrant.get_aliases()).aliases
    ours = [a for a in aliases if a.alias_name in {s.alias for s in specs}]
    assert Counter(a.alias_name for a in ours) == {s.alias: 1 for s in specs}
    assert {a.alias_name: a.collection_name for a in ours} == {s.alias: s.name for s in specs}

    info = await qdrant.get_collection(settings.qdrant_doc_chunks_alias)
    assert info.config.params.sparse_vectors is not None
    assert "bm25" in info.config.params.sparse_vectors
    assert "effective_from" in info.payload_schema


async def test_postgres_cache_and_quota(settings: Settings) -> None:
    engine = make_engine(settings.app_database_url, pool_size=1)
    sessions = async_sessionmaker(engine, expire_on_commit=False)
    model = "integration-test-model"
    inner = FakeLLMClient()
    guard = QuotaGuard(PostgresQuotaStore(sessions), {("gemini", model): 1})
    client = CachedLLMClient(inner, PostgresCacheStore(sessions), guard)
    try:
        first = await client.complete("integration prompt", model=model)
        cached = await client.complete("integration prompt", model=model)
        with pytest.raises(QuotaExceeded):
            await client.complete("a different prompt", model=model)
        remaining = await guard.remaining()
    finally:
        await engine.dispose()

    assert (first.cached, cached.cached) == (False, True)
    assert len(inner.calls) == 1
    assert remaining == {f"gemini/{model}": 0}


def test_health_endpoint_with_live_dependencies(settings: Settings) -> None:
    with TestClient(create_app(settings)) as client:
        response = client.get("/health")
    body = response.json()
    assert response.status_code == 200, body
    assert body["postgres"]["ok"] and body["qdrant"]["ok"]
    assert body["quota_remaining"] is not None
