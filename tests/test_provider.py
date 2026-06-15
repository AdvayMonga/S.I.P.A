import asyncio
from pathlib import Path

import pytest

from bot.config import Settings
from bot.provider import AnthropicProvider, LocalProvider, cost_usd, make_provider


def _settings(provider: str) -> Settings:
    return Settings(anthropic_api_key="x", vault_path=Path("/tmp"), provider=provider)


def test_factory_defaults_to_anthropic() -> None:
    assert isinstance(make_provider(_settings("anthropic")), AnthropicProvider)


def test_factory_selects_local() -> None:
    assert isinstance(make_provider(_settings("local")), LocalProvider)


def test_local_provider_not_wired_yet() -> None:
    provider = LocalProvider(_settings("local"))
    with pytest.raises(NotImplementedError):
        asyncio.run(provider.generate(system="", messages=[], tools=[]))


def test_cost_usd_opus_4_8_rates() -> None:
    # 1M input @ $5 + 1M output @ $25 = $30
    assert cost_usd(1_000_000, 1_000_000, 5.0, 25.0) == 30.0
    assert cost_usd(0, 0, 5.0, 25.0) == 0.0
    assert round(cost_usd(2000, 500, 5.0, 25.0), 4) == 0.0225
