import asyncio
import json
from types import SimpleNamespace
from typing import Any

from anthropic.types import TextBlock

from bot.cli import _persist_session, _resume_session
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


class EpisodeHost:
    def __init__(self, episodes: list[dict]) -> None:
        self._episodes = episodes

    async def call_tool(self, name: str, arguments: dict) -> tuple[str, bool]:
        return (json.dumps(self._episodes), False)


def test_resume_loads_latest_episode() -> None:
    convo = Conversation()
    host = EpisodeHost([{"content": "older"}, {"content": "latest"}])  # oldest→newest
    asyncio.run(_resume_session(convo, host))  # type: ignore[arg-type]
    assert convo.summary == "latest"


def test_resume_no_episodes_is_noop() -> None:
    convo = Conversation()
    asyncio.run(_resume_session(convo, EpisodeHost([])))  # type: ignore[arg-type]
    assert convo.summary == ""
