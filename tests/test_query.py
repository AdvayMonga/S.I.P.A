import asyncio
from types import SimpleNamespace
from typing import Any

from anthropic.types import TextBlock

from bot.conversation import Conversation
from bot.query import _needs_rewrite, _recent, rewrite_query


class FakeProvider:
    """Returns a canned rewritten query; records calls and the input it saw."""

    def __init__(self, text: str = "REWRITTEN QUERY") -> None:
        self.calls = 0
        self.text = text
        self.last_input = ""

    async def generate(self, *, system: str, messages: list, tools: list) -> Any:
        self.calls += 1
        self.last_input = messages[0]["content"]
        return SimpleNamespace(content=[TextBlock(type="text", text=self.text)])

    def usage(self) -> dict:
        return {}


class BoomProvider:
    async def generate(self, *, system: str, messages: list, tools: list) -> Any:
        raise RuntimeError("model down")

    def usage(self) -> dict:
        return {}


def _user(text: str) -> dict:
    return {"role": "user", "content": text}


def _assistant(text: str) -> dict:
    return {"role": "assistant", "content": [TextBlock(type="text", text=text)]}


def _with_history() -> Conversation:
    return Conversation(messages=[_user("tell me about my projects"), _assistant("A and B.")])


def test_no_history_returns_raw_no_call() -> None:
    provider = FakeProvider()
    out = asyncio.run(rewrite_query(provider, Conversation(), "what about the second one?"))
    assert out == "what about the second one?"
    assert provider.calls == 0


def test_referential_followup_is_rewritten() -> None:
    provider = FakeProvider()
    out = asyncio.run(rewrite_query(provider, _with_history(), "what about the second one?"))
    assert out == "REWRITTEN QUERY"
    assert provider.calls == 1


def test_short_message_is_rewritten() -> None:
    provider = FakeProvider()
    out = asyncio.run(rewrite_query(provider, _with_history(), "and the next step"))
    assert out == "REWRITTEN QUERY"
    assert provider.calls == 1


def test_standalone_message_skips_rewrite() -> None:
    provider = FakeProvider()
    msg = "how do I configure the daemon socket path in my environment file"
    out = asyncio.run(rewrite_query(provider, _with_history(), msg))
    assert out == msg
    assert provider.calls == 0


def test_provider_error_degrades_to_raw() -> None:
    out = asyncio.run(rewrite_query(BoomProvider(), _with_history(), "what about it?"))
    assert out == "what about it?"


def test_empty_rewrite_falls_back_to_raw() -> None:
    provider = FakeProvider(text="   ")
    out = asyncio.run(rewrite_query(provider, _with_history(), "what about it?"))
    assert out == "what about it?"


def test_summary_only_history_triggers_rewrite() -> None:
    provider = FakeProvider()
    convo = Conversation(summary="We discussed projects A and B.")
    out = asyncio.run(rewrite_query(provider, convo, "what about that?"))
    assert out == "REWRITTEN QUERY"
    assert provider.calls == 1


def test_needs_rewrite_gate() -> None:
    convo = _with_history()
    assert _needs_rewrite("what about it?", convo) is True
    assert _needs_rewrite("short ask", convo) is True  # <= 6 words
    standalone = "explain the obsidian vault git versioning model in detail"
    assert _needs_rewrite(standalone, convo) is False
    assert _needs_rewrite("what about it?", Conversation()) is False  # no history


def test_recent_includes_summary_and_turns() -> None:
    convo = Conversation(messages=[_user("hi there"), _assistant("hello")], summary="prior state")
    rendered = _recent(convo)
    assert "Summary so far: prior state" in rendered
    assert "user: hi there" in rendered
    assert "assistant: hello" in rendered
