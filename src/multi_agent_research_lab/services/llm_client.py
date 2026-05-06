"""LLM client abstraction.

Production note: agents should depend on this interface instead of importing an SDK directly.
"""

import os
from dataclasses import dataclass
from importlib import import_module
from typing import Any, Final

from openai import APIConnectionError, APITimeoutError, OpenAI, OpenAIError, RateLimitError
from tenacity import (
    RetryError,
    retry,
    retry_if_exception_type,
    stop_after_attempt,
    wait_exponential,
)

from multi_agent_research_lab.core.config import get_settings
from multi_agent_research_lab.core.errors import AgentExecutionError, ValidationError

_MODEL_PRICING_PER_1M_TOKENS: Final[dict[str, tuple[float, float]]] = {
    "gpt-4o-mini": (0.15, 0.60),
    "gpt-4.1-mini": (0.40, 1.60),
    "gpt-4.1-nano": (0.10, 0.40),
}


@dataclass(frozen=True)
class LLMResponse:
    content: str
    input_tokens: int | None = None
    output_tokens: int | None = None
    cost_usd: float | None = None


class LLMClient:
    """Provider-agnostic LLM client backed by OpenAI chat completions."""

    def __init__(self) -> None:
        settings = get_settings()
        self._model = settings.openai_model
        self._timeout_seconds = float(settings.timeout_seconds)
        self._client: Any = None

    @staticmethod
    def _langfuse_credentials_present() -> bool:
        settings = get_settings()
        return bool(
            settings.langfuse_enabled
            and settings.langfuse_public_key
            and settings.langfuse_secret_key
        )

    def _get_client(self) -> Any:
        if self._client is None:
            settings = get_settings()
            if not settings.openai_api_key:
                raise ValidationError("OPENAI_API_KEY is required to call LLMClient.complete")
            if self._langfuse_credentials_present():
                try:
                    langfuse_openai_module = import_module("langfuse.openai")
                    langfuse_openai_cls = langfuse_openai_module.OpenAI
                except ImportError as exc:
                    raise ValidationError(
                        "Langfuse credentials are configured, but the "
                        "langfuse package is not installed."
                    ) from exc
                os.environ["LANGFUSE_PUBLIC_KEY"] = settings.langfuse_public_key or ""
                os.environ["LANGFUSE_SECRET_KEY"] = settings.langfuse_secret_key or ""
                os.environ["LANGFUSE_BASE_URL"] = settings.langfuse_base_url
                self._client = langfuse_openai_cls(
                    api_key=settings.openai_api_key,
                    timeout=self._timeout_seconds,
                )
            else:
                self._client = OpenAI(
                    api_key=settings.openai_api_key,
                    timeout=self._timeout_seconds,
                )
        return self._client

    @staticmethod
    def _estimate_cost_usd(
        model: str,
        input_tokens: int | None,
        output_tokens: int | None,
    ) -> float | None:
        pricing = _MODEL_PRICING_PER_1M_TOKENS.get(model)
        if pricing is None or input_tokens is None or output_tokens is None:
            return None

        input_price, output_price = pricing
        return (
            (input_tokens / 1_000_000) * input_price
            + (output_tokens / 1_000_000) * output_price
        )

    @retry(
        reraise=True,
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=1, max=8),
        retry=retry_if_exception_type((APIConnectionError, APITimeoutError, RateLimitError)),
    )
    def _create_completion(self, system_prompt: str, user_prompt: str) -> Any:
        client = self._get_client()
        return client.chat.completions.create(
            model=self._model,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
        )

    def complete(self, system_prompt: str, user_prompt: str) -> LLMResponse:
        """Return a model completion.

        Retry, timeout, and token logging live here rather than inside agents.
        """

        if not system_prompt.strip():
            raise ValidationError("system_prompt must not be empty")
        if not user_prompt.strip():
            raise ValidationError("user_prompt must not be empty")

        try:
            response = self._create_completion(system_prompt=system_prompt, user_prompt=user_prompt)
        except RetryError as exc:
            raise AgentExecutionError("LLM request failed after retries") from exc
        except OpenAIError as exc:
            raise AgentExecutionError(f"LLM request failed: {exc}") from exc

        message = response.choices[0].message.content if response.choices else None
        if not message:
            raise AgentExecutionError("LLM response did not contain any message content")

        usage = response.usage
        input_tokens = usage.prompt_tokens if usage is not None else None
        output_tokens = usage.completion_tokens if usage is not None else None
        cost_usd = self._estimate_cost_usd(self._model, input_tokens, output_tokens)

        return LLMResponse(
            content=message,
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            cost_usd=cost_usd,
        )
