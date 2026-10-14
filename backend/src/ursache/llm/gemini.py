from __future__ import annotations

from google import genai
from google.genai import types
from pydantic import BaseModel

from ursache.llm.client import Completion, StructuredCompletion


class GeminiClient:
    """Gemini via the google-genai SDK. Wrap with CachedLLMClient; do not call directly."""

    provider = "gemini"

    def __init__(self, api_key: str | None = None, *, client: genai.Client | None = None) -> None:
        self._client = client or genai.Client(api_key=api_key)

    async def complete(
        self,
        prompt: str,
        *,
        model: str,
        system: str | None = None,
        temperature: float | None = None,
    ) -> Completion:
        config = types.GenerateContentConfig(system_instruction=system, temperature=temperature)
        response = await self._client.aio.models.generate_content(
            model=model, contents=prompt, config=config
        )
        return _completion(response, model)

    async def complete_structured[M: BaseModel](
        self,
        prompt: str,
        schema: type[M],
        *,
        model: str,
        system: str | None = None,
        temperature: float | None = None,
    ) -> StructuredCompletion[M]:
        config = types.GenerateContentConfig(
            system_instruction=system,
            temperature=temperature,
            response_mime_type="application/json",
            response_json_schema=schema.model_json_schema(),
        )
        response = await self._client.aio.models.generate_content(
            model=model, contents=prompt, config=config
        )
        completion = _completion(response, model)
        return StructuredCompletion(schema.model_validate_json(completion.text), completion)


def _completion(response: types.GenerateContentResponse, model: str) -> Completion:
    usage = response.usage_metadata
    tokens_in = (usage.prompt_token_count or 0) if usage else 0
    tokens_out = (
        ((usage.candidates_token_count or 0) + (usage.thoughts_token_count or 0)) if usage else 0
    )
    return Completion(
        text=response.text or "", model=model, tokens_in=tokens_in, tokens_out=tokens_out
    )
