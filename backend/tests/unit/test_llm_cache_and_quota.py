from datetime import UTC, datetime

import pytest
from pydantic import BaseModel

from tests.fakes import FakeLLMClient
from ursache.llm.cache import CachedLLMClient, InMemoryCacheStore, cache_key
from ursache.llm.quota import InMemoryQuotaStore, QuotaExceeded, QuotaGuard

MODEL = "gemini-test-flash"


class Verdict(BaseModel):
    cause: str
    confidence: float


def make_client(
    cap: int = 10, text: str = "fake answer"
) -> tuple[CachedLLMClient, FakeLLMClient, InMemoryQuotaStore]:
    inner = FakeLLMClient(text)
    quota_store = InMemoryQuotaStore()
    guard = QuotaGuard(quota_store, {("gemini", MODEL): cap})
    return CachedLLMClient(inner, InMemoryCacheStore(), guard), inner, quota_store


async def test_cache_hit_skips_the_client() -> None:
    client, inner, _ = make_client()

    first = await client.complete("why are there scale pits?", model=MODEL)
    second = await client.complete("why are there scale pits?", model=MODEL)

    assert len(inner.calls) == 1
    assert first.cached is False
    assert second.cached is True
    assert second.text == first.text
    assert second.tokens_in == first.tokens_in


async def test_stored_response_is_returned_without_calling_client() -> None:
    inner = FakeLLMClient()
    store = InMemoryCacheStore()
    guard = QuotaGuard(InMemoryQuotaStore(), {("gemini", MODEL): 0})
    client = CachedLLMClient(inner, store, guard)
    await CachedLLMClient(
        FakeLLMClient("from earlier"), store, QuotaGuard(InMemoryQuotaStore(), {})
    ).complete("prompt", model=MODEL)

    result = await client.complete("prompt", model=MODEL)

    assert result.text == "from earlier"
    assert inner.calls == []


async def test_structured_completion_is_cached_and_parsed() -> None:
    client, inner, _ = make_client(text='{"cause": "worn descaler nozzle", "confidence": 0.8}')

    first = await client.complete_structured("rca", Verdict, model=MODEL)
    second = await client.complete_structured("rca", Verdict, model=MODEL)

    assert len(inner.calls) == 1
    assert second.completion.cached is True
    assert second.value == first.value == Verdict(cause="worn descaler nozzle", confidence=0.8)


async def test_key_depends_on_model_prompt_and_params() -> None:
    base = cache_key("m", "p", {"temp": None})
    assert base == cache_key("m", "p", {"temp": None})
    assert base != cache_key("m2", "p", {"temp": None})
    assert base != cache_key("m", "p2", {"temp": None})
    assert base != cache_key("m", "p", {"temp": 0.5})


async def test_quota_guard_raises_at_cap() -> None:
    client, inner, store = make_client(cap=2)

    await client.complete("a", model=MODEL)
    await client.complete("b", model=MODEL)
    with pytest.raises(QuotaExceeded) as excinfo:
        await client.complete("c", model=MODEL)

    assert excinfo.value.cap == 2
    assert len(inner.calls) == 2
    assert sum(store.requests.values()) == 2


async def test_cache_hits_do_not_consume_quota() -> None:
    client, _, store = make_client(cap=1)

    await client.complete("same", model=MODEL)
    await client.complete("same", model=MODEL)

    assert sum(store.requests.values()) == 1


async def test_quota_records_tokens_and_reports_remaining() -> None:
    client, _, store = make_client(cap=5)
    guard = QuotaGuard(store, {("gemini", MODEL): 5})

    await client.complete("x", model=MODEL)

    assert sum(store.tokens.values()) == 15
    assert await guard.remaining() == {f"gemini/{MODEL}": 4}


async def test_quota_day_follows_configured_timezone() -> None:
    late_utc = datetime(2026, 1, 2, 5, 0, tzinfo=UTC)  # still Jan 1 in Los Angeles
    guard = QuotaGuard(
        InMemoryQuotaStore(), {}, timezone="America/Los_Angeles", clock=lambda: late_utc
    )
    assert guard.today().isoformat() == "2026-01-01"


async def test_uncapped_models_are_not_limited() -> None:
    guard = QuotaGuard(InMemoryQuotaStore(), {})
    for _ in range(100):
        await guard.acquire("gemini", "some-other-model")
