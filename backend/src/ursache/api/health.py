from __future__ import annotations

import asyncio
import time
from collections.abc import AsyncGenerator, Awaitable, Callable
from contextlib import asynccontextmanager
from typing import Literal

from pydantic import BaseModel
from qdrant_client import AsyncQdrantClient
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine, async_sessionmaker

from ursache.config import Settings
from ursache.db.session import make_engine
from ursache.indexing.qdrant_bootstrap import make_qdrant_client
from ursache.llm.quota import PostgresQuotaStore, QuotaGuard

PROBE_TIMEOUT_S = 5.0


class DependencyStatus(BaseModel):
    ok: bool
    latency_ms: float
    error: str | None = None


class HealthReport(BaseModel):
    status: Literal["ok", "degraded"]
    postgres: DependencyStatus
    qdrant: DependencyStatus
    quota_remaining: dict[str, int] | None


class HealthService:
    def __init__(self, engine: AsyncEngine, qdrant: AsyncQdrantClient, quota: QuotaGuard) -> None:
        self._engine = engine
        self._qdrant = qdrant
        self.quota = quota

    async def check(self) -> HealthReport:
        postgres = await self._probe(self._ping_postgres)
        qdrant = await self._probe(self._ping_qdrant)
        quota = None
        if postgres.ok:
            try:
                quota = await self.quota.remaining()
            except Exception:  # noqa: BLE001  quota display must not fail the health check
                quota = None
        return HealthReport(
            status="ok" if postgres.ok and qdrant.ok else "degraded",
            postgres=postgres,
            qdrant=qdrant,
            quota_remaining=quota,
        )

    async def _ping_postgres(self) -> None:
        async with self._engine.connect() as conn:
            await conn.execute(text("SELECT 1"))

    async def _ping_qdrant(self) -> None:
        await self._qdrant.get_collections()

    @staticmethod
    async def _probe(fn: Callable[[], Awaitable[None]]) -> DependencyStatus:
        start = time.perf_counter()
        try:
            async with asyncio.timeout(PROBE_TIMEOUT_S):
                await fn()
        except Exception as exc:  # noqa: BLE001
            return DependencyStatus(
                ok=False,
                latency_ms=round((time.perf_counter() - start) * 1000, 1),
                error=type(exc).__name__,
            )
        return DependencyStatus(ok=True, latency_ms=round((time.perf_counter() - start) * 1000, 1))


@asynccontextmanager
async def health_service(settings: Settings) -> AsyncGenerator[HealthService, None]:
    engine = make_engine(settings.app_database_url, pool_size=2)
    qdrant = make_qdrant_client(settings)
    quota = QuotaGuard(
        PostgresQuotaStore(async_sessionmaker(engine, expire_on_commit=False)),
        settings.daily_caps(),
        timezone=settings.quota_timezone,
    )
    try:
        yield HealthService(engine, qdrant, quota)
    finally:
        await qdrant.close()
        await engine.dispose()
