from __future__ import annotations

from collections.abc import Callable, Mapping
from datetime import UTC, date, datetime
from typing import Protocol
from zoneinfo import ZoneInfo

from sqlalchemy import select, update
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from ursache.db.models.app import QuotaUsage


class QuotaExceeded(Exception):
    def __init__(self, provider: str, model: str, cap: int) -> None:
        super().__init__(f"daily quota reached for {provider}/{model} (cap {cap})")
        self.provider = provider
        self.model = model
        self.cap = cap


class QuotaStore(Protocol):
    async def reserve(self, day: date, provider: str, model: str, cap: int) -> bool:
        """Atomically count one request if usage is below cap. Returns False at the cap."""
        ...

    async def add_tokens(self, day: date, provider: str, model: str, tokens: int) -> None: ...

    async def used(self, day: date, provider: str, model: str) -> int: ...


class InMemoryQuotaStore:
    def __init__(self) -> None:
        self.requests: dict[tuple[date, str, str], int] = {}
        self.tokens: dict[tuple[date, str, str], int] = {}

    async def reserve(self, day: date, provider: str, model: str, cap: int) -> bool:
        key = (day, provider, model)
        if self.requests.get(key, 0) >= cap:
            return False
        self.requests[key] = self.requests.get(key, 0) + 1
        return True

    async def add_tokens(self, day: date, provider: str, model: str, tokens: int) -> None:
        key = (day, provider, model)
        self.tokens[key] = self.tokens.get(key, 0) + tokens

    async def used(self, day: date, provider: str, model: str) -> int:
        return self.requests.get((day, provider, model), 0)


class PostgresQuotaStore:
    def __init__(self, sessionmaker: async_sessionmaker[AsyncSession]) -> None:
        self._sessionmaker = sessionmaker

    async def reserve(self, day: date, provider: str, model: str, cap: int) -> bool:
        if cap <= 0:
            return False
        stmt = (
            pg_insert(QuotaUsage)
            .values(day=day, provider=provider, model=model, requests=1, tokens=0)
            .on_conflict_do_update(
                index_elements=[QuotaUsage.day, QuotaUsage.provider, QuotaUsage.model],
                set_={"requests": QuotaUsage.requests + 1},
                where=QuotaUsage.requests < cap,
            )
            .returning(QuotaUsage.requests)
        )
        async with self._sessionmaker.begin() as session:
            return (await session.execute(stmt)).scalar_one_or_none() is not None

    async def add_tokens(self, day: date, provider: str, model: str, tokens: int) -> None:
        stmt = (
            update(QuotaUsage)
            .where(
                QuotaUsage.day == day, QuotaUsage.provider == provider, QuotaUsage.model == model
            )
            .values(tokens=QuotaUsage.tokens + tokens)
        )
        async with self._sessionmaker.begin() as session:
            await session.execute(stmt)

    async def used(self, day: date, provider: str, model: str) -> int:
        stmt = select(QuotaUsage.requests).where(
            QuotaUsage.day == day, QuotaUsage.provider == provider, QuotaUsage.model == model
        )
        async with self._sessionmaker() as session:
            return (await session.execute(stmt)).scalar_one_or_none() or 0


class QuotaGuard:
    """Enforces per-model daily request caps. Models without a configured cap are unlimited."""

    def __init__(
        self,
        store: QuotaStore,
        caps: Mapping[tuple[str, str], int],
        *,
        timezone: str = "UTC",
        clock: Callable[[], datetime] = lambda: datetime.now(UTC),
    ) -> None:
        self._store = store
        self._caps = dict(caps)
        self._tz = ZoneInfo(timezone)
        self._clock = clock

    def today(self) -> date:
        return self._clock().astimezone(self._tz).date()

    async def acquire(self, provider: str, model: str) -> None:
        cap = self._caps.get((provider, model))
        if cap is None:
            return
        if not await self._store.reserve(self.today(), provider, model, cap):
            raise QuotaExceeded(provider, model, cap)

    async def record_tokens(self, provider: str, model: str, tokens: int) -> None:
        if (provider, model) in self._caps and tokens:
            await self._store.add_tokens(self.today(), provider, model, tokens)

    async def remaining(self) -> dict[str, int]:
        day = self.today()
        return {
            f"{provider}/{model}": max(cap - await self._store.used(day, provider, model), 0)
            for (provider, model), cap in self._caps.items()
        }
