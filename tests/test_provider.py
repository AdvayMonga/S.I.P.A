import asyncio
from pathlib import Path

import pytest

from bot.config import Settings
from bot.provider import AnthropicProvider, LocalProvider, make_provider


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
