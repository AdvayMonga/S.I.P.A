"""ModelProvider interface + Anthropic implementation (the brain seam)."""

import logging
from typing import Any, Protocol

from anthropic import AsyncAnthropic
from anthropic.types import Message

from .config import Settings

_cost_log = logging.getLogger("sipa.cost")


def cost_usd(input_tokens: int, output_tokens: int, in_price: float, out_price: float) -> float:
    """Dollar cost of a token count given per-million-token prices."""
    return (input_tokens * in_price + output_tokens * out_price) / 1_000_000


class ModelProvider(Protocol):
    """One call: system + history + tools -> a model response."""

    async def generate(
        self, *, system: str, messages: list[Any], tools: list[Any]
    ) -> Message: ...

    def usage(self) -> dict[str, Any]:
        """Running session token/cost totals + the last call's delta (for telemetry)."""
        ...


class AnthropicProvider:
    """Claude via the official SDK. The default ModelProvider."""

    def __init__(self, settings: Settings) -> None:
        self._client = AsyncAnthropic(api_key=settings.anthropic_api_key)
        self._model = settings.model
        self._max_tokens = settings.max_tokens
        self._thinking = settings.thinking
        self._in_price = settings.input_price_per_mtok
        self._out_price = settings.output_price_per_mtok
        self._in_tokens = 0  # running session totals
        self._out_tokens = 0
        self._last_in = 0  # the most recent call's delta
        self._last_out = 0

    async def generate(
        self, *, system: str, messages: list[Any], tools: list[Any]
    ) -> Message:
        extra: dict[str, Any] = {"thinking": {"type": "adaptive"}} if self._thinking else {}
        message = await self._client.messages.create(
            model=self._model,
            max_tokens=self._max_tokens,
            system=system,
            messages=messages,
            tools=tools,
            **extra,
        )
        usage = message.usage
        self._last_in = usage.input_tokens
        self._last_out = usage.output_tokens
        self._in_tokens += usage.input_tokens
        self._out_tokens += usage.output_tokens
        session = cost_usd(self._in_tokens, self._out_tokens, self._in_price, self._out_price)
        _cost_log.info(
            "tokens in=%d out=%d | session %d/%d ≈ $%.4f",
            usage.input_tokens,
            usage.output_tokens,
            self._in_tokens,
            self._out_tokens,
            session,
        )
        return message

    def usage(self) -> dict[str, Any]:
        session = cost_usd(self._in_tokens, self._out_tokens, self._in_price, self._out_price)
        return {
            "in_tokens": self._in_tokens,
            "out_tokens": self._out_tokens,
            "last_in": self._last_in,
            "last_out": self._last_out,
            "cost_usd": session,
        }


class LocalProvider:
    """Scaffold for a fully-local model (no data leaves the device). Not wired yet — selecting
    provider='local' reserves the seam for a future local runtime (llama.cpp / Ollama)."""

    def __init__(self, settings: Settings) -> None:
        self._model = settings.model

    async def generate(self, *, system: str, messages: list[Any], tools: list[Any]) -> Message:
        raise NotImplementedError(
            "LocalProvider is a scaffold — wire a local runtime before selecting provider='local'."
        )

    def usage(self) -> dict[str, Any]:
        return {"in_tokens": 0, "out_tokens": 0, "last_in": 0, "last_out": 0, "cost_usd": 0.0}


def make_provider(settings: Settings) -> ModelProvider:
    """Pick the provider from config — the brain seam (VISION §5.4)."""
    return LocalProvider(settings) if settings.provider == "local" else AnthropicProvider(settings)
