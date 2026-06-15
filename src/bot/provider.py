"""ModelProvider interface + Anthropic implementation (the brain seam)."""

import logging
from typing import Any, Protocol

from anthropic import AsyncAnthropic
from anthropic.types import Message

from .config import Settings

_cost_log = logging.getLogger("sipa.cost")


class ModelProvider(Protocol):
    """One call: system + history + tools -> a model response."""

    async def generate(
        self, *, system: str, messages: list[Any], tools: list[Any]
    ) -> Message: ...


class AnthropicProvider:
    """Claude via the official SDK. The default ModelProvider."""

    def __init__(self, settings: Settings) -> None:
        self._client = AsyncAnthropic(api_key=settings.anthropic_api_key)
        self._model = settings.model
        self._max_tokens = settings.max_tokens

    async def generate(
        self, *, system: str, messages: list[Any], tools: list[Any]
    ) -> Message:
        message = await self._client.messages.create(
            model=self._model,
            max_tokens=self._max_tokens,
            system=system,
            messages=messages,
            tools=tools,
        )
        usage = message.usage
        _cost_log.info("tokens in=%d out=%d", usage.input_tokens, usage.output_tokens)
        return message
