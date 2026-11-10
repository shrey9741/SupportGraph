"""Provider-agnostic LLM layer.

Every agent calls `llm.structured(schema, system, user)` and gets back a
validated Pydantic object or an LLMError. Retries and validation live here so
the nodes stay simple. `calls` counts every attempt (the action budget).
"""
import time
from typing import TypeVar

from pydantic import BaseModel

from .config import Settings

T = TypeVar("T", bound=BaseModel)


class LLMError(Exception):
    """Raised when a structured call still fails after all attempts."""


class LLMClient:
    def __init__(self, max_attempts: int = 3, backoff_s: float = 1.0):
        self.max_attempts = max(1, max_attempts)
        self.backoff_s = backoff_s
        self.calls = 0

    def _call(self, schema: type[T], system: str, user: str):
        raise NotImplementedError

    def structured(self, schema: type[T], system: str, user: str) -> T:
        last: Exception | None = None
        for attempt in range(1, self.max_attempts + 1):
            self.calls += 1
            try:
                out = self._call(schema, system, user)
                data = out.model_dump() if isinstance(out, BaseModel) else out
                return schema.model_validate(data)
            except Exception as e:  # noqa: BLE001  malformed output, rate limit, network
                last = e
                if attempt < self.max_attempts and self.backoff_s > 0:
                    time.sleep(self.backoff_s * 2 ** (attempt - 1))
        raise LLMError(f"{type(last).__name__}: {last}") from last


class GroqLLM(LLMClient):
    def __init__(self, model: str, api_key: str, **kwargs):
        super().__init__(**kwargs)
        from langchain_groq import ChatGroq

        self._chat = ChatGroq(model=model, api_key=api_key, temperature=0)

    def _call(self, schema: type[T], system: str, user: str):
        runnable = self._chat.with_structured_output(schema)
        return runnable.invoke([("system", system), ("human", user)])


def make_llm(settings: Settings) -> LLMClient:
    if settings.llm_provider == "stub":
        from .stub_llm import StubLLM

        return StubLLM()
    if settings.llm_provider == "groq":
        if not settings.groq_api_key:
            raise RuntimeError("LLM_PROVIDER=groq but GROQ_API_KEY is not set in .env")
        return GroqLLM(settings.llm_model, settings.groq_api_key, max_attempts=settings.max_llm_attempts)
    raise RuntimeError(f"Unknown LLM_PROVIDER: {settings.llm_provider!r}")
