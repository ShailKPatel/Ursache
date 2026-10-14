from __future__ import annotations

from pydantic import BaseModel

from ursache.llm.client import Completion, StructuredCompletion


class FakeLLMClient:
    """Deterministic LLMClient for tests; records every call it receives."""

    provider = "gemini"

    def __init__(self, text: str = "fake answer") -> None:
        self.text = text
        self.calls: list[str] = []

    async def complete(
        self,
        prompt: str,
        *,
        model: str,
        system: str | None = None,
        temperature: float | None = None,
    ) -> Completion:
        self.calls.append(prompt)
        return Completion(text=self.text, model=model, tokens_in=10, tokens_out=5)

    async def complete_structured[M: BaseModel](
        self,
        prompt: str,
        schema: type[M],
        *,
        model: str,
        system: str | None = None,
        temperature: float | None = None,
    ) -> StructuredCompletion[M]:
        self.calls.append(prompt)
        completion = Completion(text=self.text, model=model, tokens_in=10, tokens_out=5)
        return StructuredCompletion(schema.model_validate_json(self.text), completion)
