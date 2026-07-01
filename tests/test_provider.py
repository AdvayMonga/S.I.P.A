import asyncio
from pathlib import Path

import pytest

from bot.config import Settings
from bot.provider import (
    AnthropicProvider,
    LocalProvider,
    _cache_messages,
    _cache_tools,
    cost_usd,
    make_provider,
    session_cost_usd,
)


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


def test_cache_tools_marks_last_only_without_mutating() -> None:
    tools = [{"name": "a"}, {"name": "b"}]
    out = _cache_tools(tools)
    assert out[-1]["cache_control"] == {"type": "ephemeral"}
    assert "cache_control" not in out[0]
    assert tools == [{"name": "a"}, {"name": "b"}]  # caller's list untouched


def test_cache_tools_empty_is_noop() -> None:
    assert _cache_tools([]) == []


def test_cache_messages_wraps_string_content_without_mutating() -> None:
    messages = [{"role": "user", "content": "hello"}]
    out = _cache_messages(messages)
    assert out[-1]["content"] == [
        {"type": "text", "text": "hello", "cache_control": {"type": "ephemeral"}}
    ]
    assert messages == [{"role": "user", "content": "hello"}]  # caller's list untouched


def test_cache_messages_marks_last_block_of_tool_result_list() -> None:
    tr = {"type": "tool_result", "tool_use_id": "t1", "content": "out", "is_error": False}
    messages = [{"role": "user", "content": "hi"}, {"role": "user", "content": [tr]}]
    out = _cache_messages(messages)
    assert out[-1]["content"][-1]["cache_control"] == {"type": "ephemeral"}
    assert out[0]["content"] == "hi"  # earlier messages untouched (string stays a string)
    assert "cache_control" not in tr  # original block untouched


def test_cache_messages_empty_is_noop() -> None:
    assert _cache_messages([]) == []


def test_cost_usd_opus_4_8_rates() -> None:
    # 1M input @ $5 + 1M output @ $25 = $30
    assert cost_usd(1_000_000, 1_000_000, 5.0, 25.0) == 30.0
    assert cost_usd(0, 0, 5.0, 25.0) == 0.0
    assert round(cost_usd(2000, 500, 5.0, 25.0), 4) == 0.0225


def test_session_cost_bills_cache_tiers() -> None:
    # No cache → identical to flat cost_usd.
    assert session_cost_usd(2000, 500, 0, 0, 5.0, 25.0) == cost_usd(2000, 500, 5.0, 25.0)
    # Reads bill at 0.1x, writes at 1.25x base input.
    # 1M reads @ $5*0.1 = $0.5 ; 1M writes @ $5*1.25 = $6.25
    assert session_cost_usd(0, 0, 1_000_000, 0, 5.0, 25.0) == 0.5
    assert session_cost_usd(0, 0, 0, 1_000_000, 5.0, 25.0) == 6.25
