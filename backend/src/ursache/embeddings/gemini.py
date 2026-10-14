from __future__ import annotations

from collections.abc import Sequence

from google import genai
from google.genai import types

from ursache.llm.quota import QuotaGuard

# gemini-embedding-2 takes no task_type; the task is expressed as a text prefix instead.
_QUERY_PREFIX = "task: search result | query: "


class GeminiEmbedder:
    """Text and image embeddings in one shared space (gemini-embedding-2)."""

    provider = "gemini"

    def __init__(
        self,
        *,
        model: str,
        dim: int,
        api_key: str | None = None,
        quota: QuotaGuard | None = None,
        client: genai.Client | None = None,
    ) -> None:
        self.model_version = f"{model}@{dim}"
        self.dim = dim
        self._model = model
        self._quota = quota
        self._client = client or genai.Client(api_key=api_key)

    async def embed_documents(
        self, texts: Sequence[str], titles: Sequence[str | None] | None = None
    ) -> list[list[float]]:
        titles = titles or [None] * len(texts)
        if len(titles) != len(texts):
            raise ValueError("titles and texts must have the same length")
        formatted = [
            f"title: {t or 'none'} | text: {x}" for t, x in zip(titles, texts, strict=True)
        ]
        return await self._embed([types.Part.from_text(text=x) for x in formatted])

    async def embed_query(self, text: str) -> list[float]:
        return (await self._embed([types.Part.from_text(text=_QUERY_PREFIX + text)]))[0]

    async def embed_images(
        self, images: Sequence[bytes], mime_type: str = "image/png"
    ) -> list[list[float]]:
        return await self._embed(
            [types.Part.from_bytes(data=b, mime_type=mime_type) for b in images]
        )

    async def _embed(self, parts: list[types.Part]) -> list[list[float]]:
        if not parts:
            return []
        if self._quota is not None:
            await self._quota.acquire(self.provider, self._model)
        # One Content per input: passing bare parts would return a single aggregated embedding.
        response = await self._client.aio.models.embed_content(
            model=self._model,
            contents=[types.Content(parts=[p]) for p in parts],
            config=types.EmbedContentConfig(output_dimensionality=self.dim),
        )
        vectors = [e.values or [] for e in response.embeddings or []]
        if len(vectors) != len(parts):
            raise RuntimeError(f"expected {len(parts)} embeddings, got {len(vectors)}")
        return vectors
