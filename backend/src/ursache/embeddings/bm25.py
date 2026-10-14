from __future__ import annotations

from collections.abc import Sequence
from functools import cached_property
from typing import TYPE_CHECKING

from qdrant_client import models

from ursache.config import Settings
from ursache.embeddings.protocols import SparseEncoder, SparseInput

if TYPE_CHECKING:
    from fastembed import SparseTextEmbedding


class CloudBM25Encoder:
    """Qdrant Cloud Inference computes BM25 server-side; we only send the raw text."""

    def __init__(self, model: str = "qdrant/bm25") -> None:
        self.model_version = model
        self._model = model

    def encode_documents(self, texts: Sequence[str]) -> list[SparseInput]:
        return [models.Document(text=t, model=self._model) for t in texts]

    def encode_query(self, text: str) -> SparseInput:
        return models.Document(text=text, model=self._model)


class LocalBM25Encoder:
    """fastembed BM25 for local development. The tokenizer files load lazily on first use."""

    def __init__(self, model: str = "Qdrant/bm25") -> None:
        self.model_version = model
        self._model_name = model

    @cached_property
    def _model(self) -> SparseTextEmbedding:
        from fastembed import SparseTextEmbedding

        return SparseTextEmbedding(model_name=self._model_name)

    def encode_documents(self, texts: Sequence[str]) -> list[SparseInput]:
        return [
            models.SparseVector(indices=e.indices.tolist(), values=e.values.tolist())
            for e in self._model.embed(list(texts))
        ]

    def encode_query(self, text: str) -> SparseInput:
        e = next(iter(self._model.query_embed(text)))
        return models.SparseVector(indices=e.indices.tolist(), values=e.values.tolist())


def make_sparse_encoder(settings: Settings) -> SparseEncoder:
    if settings.qdrant_cloud_inference:
        return CloudBM25Encoder(settings.bm25_cloud_model)
    return LocalBM25Encoder(settings.bm25_local_model)
