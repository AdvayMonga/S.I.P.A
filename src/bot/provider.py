"""ModelProvider interface + Anthropic implementation (the brain seam)."""

import logging
from typing import Any, Protocol

from anthropic import AsyncAnthropic
from anthropic.types import Message

from .config import Settings

_cost_log = logging.getLogger("sipa.cost")


CACHE_WRITE_MULT = 1.25  # ephemeral (5m) cache writes bill at 1.25x base input
CACHE_READ_MULT = 0.10  # cache reads bill at 0.1x base input — the savings


def cost_usd(input_tokens: int, output_tokens: int, in_price: float, out_price: float) -> float:
    """Dollar cost of a token count given per-million-token prices."""
    return (input_tokens * in_price + output_tokens * out_price) / 1_000_000


def session_cost_usd(
    in_tokens: int,
    out_tokens: int,
    cache_read: int,
    cache_write: int,
    in_price: float,
    out_price: float,
) -> float:
    """Real dollar cost incl. cache tiers: uncached input full, writes 1.25x, reads 0.1x."""
    billed_input = in_tokens + cache_write * CACHE_WRITE_MULT + cache_read * CACHE_READ_MULT
    return (billed_input * in_price + out_tokens * out_price) / 1_000_000


def _cache_tools(tools: list[Any]) -> list[Any]:
    """Mark the final tool with an ephemeral cache breakpoint so the whole (static) tool prefix
    is cached — tools are ~the largest byte-stable chunk of every turn. Copy, don't mutate."""
    if not tools:
        return tools
    return [*tools[:-1], {**tools[-1], "cache_control": {"type": "ephemeral"}}]


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
        self._cache_read = 0  # running cached-input totals (the savings, for telemetry)
        self._cache_write = 0

    async def generate(
        self, *, system: str, messages: list[Any], tools: list[Any]
    ) -> Message:
        extra: dict[str, Any] = {"thinking": {"type": "adaptive"}} if self._thinking else {}
        message = await self._client.messages.create(
            model=self._model,
            max_tokens=self._max_tokens,
            system=system,
            messages=messages,
            tools=_cache_tools(tools),
            **extra,
        )
        usage = message.usage
        # input_tokens already excludes cached reads; cache fields are None pre-cache-hit.
        read = getattr(usage, "cache_read_input_tokens", None) or 0
        write = getattr(usage, "cache_creation_input_tokens", None) or 0
        self._last_in = usage.input_tokens
        self._last_out = usage.output_tokens
        self._in_tokens += usage.input_tokens
        self._out_tokens += usage.output_tokens
        self._cache_read += read
        self._cache_write += write
        session = self._session_cost()
        _cost_log.info(
            "tokens in=%d out=%d cache(r=%d w=%d) | session %d/%d ≈ $%.4f",
            usage.input_tokens,
            usage.output_tokens,
            read,
            write,
            self._in_tokens,
            self._out_tokens,
            session,
        )
        return message

    def _session_cost(self) -> float:
        return session_cost_usd(
            self._in_tokens,
            self._out_tokens,
            self._cache_read,
            self._cache_write,
            self._in_price,
            self._out_price,
        )

    def usage(self) -> dict[str, Any]:
        return {
            "in_tokens": self._in_tokens,
            "out_tokens": self._out_tokens,
            "last_in": self._last_in,
            "last_out": self._last_out,
            "cache_read": self._cache_read,
            "cache_write": self._cache_write,
            "cost_usd": self._session_cost(),
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
