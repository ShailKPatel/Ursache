from __future__ import annotations

from collections.abc import Sequence

import cohere

from ursache.embeddings.protocols import RerankResult
from ursache.llm.quota import QuotaGuard


class CohereReranker:
    provider = "cohere"

    def __init__(
        self,
        *,
        model: str,
        api_key: str | None = None,
        quota: QuotaGuard | None = None,
        client: cohere.AsyncClientV2 | None = None,
    ) -> None:
        self.model_version = model
        self._model = model
        self._quota = quota
        self._client = client or cohere.AsyncClientV2(api_key=api_key)

    async def rerank(self, query: str, documents: Sequence[str], top_n: int) -> list[RerankResult]:
        if not documents:
            return []
        if self._quota is not None:
            await self._quota.acquire(self.provider, self._model)
        response = await self._client.rerank(
            model=self._model, query=query, documents=list(documents), top_n=top_n
        )
        return [RerankResult(index=r.index, score=r.relevance_score) for r in response.results]
