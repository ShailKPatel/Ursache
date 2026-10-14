from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from typing import Protocol

from qdrant_client import models

# Client-side sparse vector, or a Document that Qdrant Cloud Inference embeds server-side.
SparseInput = models.SparseVector | models.Document


@dataclass(frozen=True, slots=True)
class RerankResult:
    index: int
    score: float


class TextEmbedder(Protocol):
    model_version: str
    dim: int

    async def embed_documents(
        self, texts: Sequence[str], titles: Sequence[str | None] | None = None
    ) -> list[list[float]]: ...

    async def embed_query(self, text: str) -> list[float]: ...


class ImageEmbedder(Protocol):
    model_version: str
    dim: int

    async def embed_images(
        self, images: Sequence[bytes], mime_type: str = "image/png"
    ) -> list[list[float]]: ...


class SparseEncoder(Protocol):
    model_version: str

    def encode_documents(self, texts: Sequence[str]) -> list[SparseInput]: ...

    def encode_query(self, text: str) -> SparseInput: ...


class Reranker(Protocol):
    model_version: str

    async def rerank(
        self, query: str, documents: Sequence[str], top_n: int
    ) -> list[RerankResult]: ...
