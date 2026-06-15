import asyncio
from types import SimpleNamespace
from typing import Any

from anthropic.types import TextBlock

from bot.cli import _persist_session
from bot.conversation import Conversation


class FakeProvider:
    async def generate(self, *, system: str, messages: list, tools: list) -> Any:
        return SimpleNamespace(content=[TextBlock(type="text", text="SESSION SUMMARY")])


class RecordingHost:
    def __init__(self) -> None:
        self.calls: list[tuple[str, dict]] = []

    async def call_tool(self, name: str, arguments: dict) -> tuple[str, bool]:
        self.calls.append((name, arguments))
        return ("ok", False)


def test_persist_writes_episode() -> None:
    convo = Conversation(messages=[{"role": "user", "content": "hi"}])
    host = RecordingHost()
    asyncio.run(_persist_session(convo, FakeProvider(), host))  # type: ignore[arg-type]
    assert host.calls == [
        ("memory_remember", {"content": "SESSION SUMMARY", "kind": "episode"})
    ]


def test_persist_skips_empty_session() -> None:
    host = RecordingHost()
    asyncio.run(_persist_session(Conversation(), FakeProvider(), host))  # type: ignore[arg-type]
    assert host.calls == []  # nothing said → nothing saved
