from __future__ import annotations

import hashlib
import json
from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any, Protocol

from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from ursache.db.models.app import LLMCacheEntry
from ursache.llm.client import Completion, LLMClient, StructuredCompletion
from ursache.llm.quota import QuotaGuard


def cache_key(model: str, prompt: str, params: Mapping[str, Any]) -> str:
    canonical = json.dumps(
        {"model": model, "prompt": prompt, "params": params},
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
    )
    return hashlib.sha256(canonical.encode()).hexdigest()


@dataclass(frozen=True, slots=True)
class CachedResponse:
    text: str
    model: str
    tokens_in: int
    tokens_out: int


class CacheStore(Protocol):
    async def get(self, key: str) -> CachedResponse | None: ...
    async def put(self, key: str, response: CachedResponse) -> None: ...


class InMemoryCacheStore:
    def __init__(self) -> None:
        self.entries: dict[str, CachedResponse] = {}

    async def get(self, key: str) -> CachedResponse | None:
        return self.entries.get(key)

    async def put(self, key: str, response: CachedResponse) -> None:
        self.entries.setdefault(key, response)


class PostgresCacheStore:
    def __init__(self, sessionmaker: async_sessionmaker[AsyncSession]) -> None:
        self._sessionmaker = sessionmaker

    async def get(self, key: str) -> CachedResponse | None:
        async with self._sessionmaker() as session:
            row = (
                await session.execute(select(LLMCacheEntry).where(LLMCacheEntry.key == key))
            ).scalar_one_or_none()
        if row is None:
            return None
        return CachedResponse(
            text=str(row.response["text"]),
            model=row.model,
            tokens_in=row.tokens_in,
            tokens_out=row.tokens_out,
        )

    async def put(self, key: str, response: CachedResponse) -> None:
        stmt = (
            pg_insert(LLMCacheEntry)
            .values(
                key=key,
                model=response.model,
                response={"text": response.text},
                tokens_in=response.tokens_in,
                tokens_out=response.tokens_out,
            )
            .on_conflict_do_nothing(index_elements=[LLMCacheEntry.key])
        )
        async with self._sessionmaker.begin() as session:
            await session.execute(stmt)


class CachedLLMClient:
    """Wraps an LLMClient: cache lookup first, then quota check, then the real call."""

    def __init__(self, inner: LLMClient, store: CacheStore, quota: QuotaGuard) -> None:
        self._inner = inner
        self._store = store
        self._quota = quota
        self.provider = inner.provider

    async def complete(
        self,
        prompt: str,
        *,
        model: str,
        system: str | None = None,
        temperature: float | None = None,
    ) -> Completion:
        key = cache_key(model, prompt, {"kind": "text", "system": system, "temp": temperature})
        if (hit := await self._store.get(key)) is not None:
            return _from_cache(hit)
        await self._quota.acquire(self.provider, model)
        completion = await self._inner.complete(
            prompt, model=model, system=system, temperature=temperature
        )
        await self._after_call(key, completion)
        return completion

    async def complete_structured[M: BaseModel](
        self,
        prompt: str,
        schema: type[M],
        *,
        model: str,
        system: str | None = None,
        temperature: float | None = None,
    ) -> StructuredCompletion[M]:
        params = {
            "kind": "structured",
            "system": system,
            "temp": temperature,
            "schema": schema.model_json_schema(),
        }
        key = cache_key(model, prompt, params)
        if (hit := await self._store.get(key)) is not None:
            return StructuredCompletion(schema.model_validate_json(hit.text), _from_cache(hit))
        await self._quota.acquire(self.provider, model)
        result = await self._inner.complete_structured(
            prompt, schema, model=model, system=system, temperature=temperature
        )
        await self._after_call(key, result.completion)
        return result

    async def _after_call(self, key: str, completion: Completion) -> None:
        await self._quota.record_tokens(
            self.provider, completion.model, completion.tokens_in + completion.tokens_out
        )
        await self._store.put(
            key,
            CachedResponse(
                text=completion.text,
                model=completion.model,
                tokens_in=completion.tokens_in,
                tokens_out=completion.tokens_out,
            ),
        )


def _from_cache(hit: CachedResponse) -> Completion:
    return Completion(
        text=hit.text,
        model=hit.model,
        tokens_in=hit.tokens_in,
        tokens_out=hit.tokens_out,
        cached=True,
    )
