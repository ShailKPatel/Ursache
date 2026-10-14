from __future__ import annotations

from collections.abc import AsyncIterator
from functools import lru_cache

from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from ursache.config import get_settings


def make_engine(url: str, *, pool_size: int = 5) -> AsyncEngine:
    # pool_pre_ping: Neon suspends idle computes and drops their connections.
    return create_async_engine(url, pool_size=pool_size, max_overflow=5, pool_pre_ping=True)


@lru_cache
def get_app_engine() -> AsyncEngine:
    return make_engine(get_settings().app_database_url)


@lru_cache
def get_agent_engine() -> AsyncEngine:
    """Read-only engine for agent tools; the role enforces SELECT-only and a 5s timeout."""
    return make_engine(get_settings().agent_database_url, pool_size=2)


@lru_cache
def get_app_sessionmaker() -> async_sessionmaker[AsyncSession]:
    return async_sessionmaker(get_app_engine(), expire_on_commit=False)


@lru_cache
def get_agent_sessionmaker() -> async_sessionmaker[AsyncSession]:
    return async_sessionmaker(get_agent_engine(), expire_on_commit=False)


async def app_session() -> AsyncIterator[AsyncSession]:
    async with get_app_sessionmaker()() as session:
        yield session


async def dispose_engines() -> None:
    for factory in (get_app_engine, get_agent_engine):
        if factory.cache_info().currsize:
            await factory().dispose()
