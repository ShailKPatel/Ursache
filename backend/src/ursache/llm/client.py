from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol

from pydantic import BaseModel


@dataclass(frozen=True, slots=True)
class Completion:
    text: str
    model: str
    tokens_in: int
    tokens_out: int
    cached: bool = False


@dataclass(frozen=True, slots=True)
class StructuredCompletion[M: BaseModel]:
    value: M
    completion: Completion


class LLMClient(Protocol):
    provider: str

    async def complete(
        self,
        prompt: str,
        *,
        model: str,
        system: str | None = None,
        temperature: float | None = None,
    ) -> Completion: ...

    async def complete_structured[M: BaseModel](
        self,
        prompt: str,
        schema: type[M],
        *,
        model: str,
        system: str | None = None,
        temperature: float | None = None,
    ) -> StructuredCompletion[M]: ...
