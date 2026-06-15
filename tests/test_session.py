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


class FakeHost:
    """Returns canned episodes for memory_list; records every call."""

    def __init__(self, episodes: list[dict] | None = None) -> None:
        self.episodes = episodes or []
        self.calls: list[tuple[str, dict]] = []

    async def call_tool(self, name: str, arguments: dict) -> tuple[str, bool]:
        self.calls.append((name, arguments))
        if name == "memory_list":
            return (json.dumps(self.episodes), False)
        return ("ok", False)

    def writes(self) -> list[tuple[str, dict]]:
        return [c for c in self.calls if c[0] in ("memory_remember", "memory_update")]


def _run(convo: Conversation, host: FakeHost) -> None:
    asyncio.run(_persist_session(convo, FakeProvider(), host))  # type: ignore[arg-type]


def test_persist_creates_when_none() -> None:
    convo = Conversation(messages=[{"role": "user", "content": "hi"}])
    host = FakeHost(episodes=[])
    _run(convo, host)
    assert host.writes() == [
        (
            "memory_remember",
            {"content": "SESSION SUMMARY", "kind": "episode", "keys": "session-summary"},
        )
    ]


def test_persist_supersedes_existing() -> None:
    convo = Conversation(messages=[{"role": "user", "content": "hi"}])
    host = FakeHost(episodes=[{"id": 5, "content": "old", "keys": "session-summary"}])
    _run(convo, host)
    assert host.writes() == [("memory_update", {"id": 5, "content": "SESSION SUMMARY"})]


def test_persist_ignores_foreign_episodes() -> None:
    convo = Conversation(messages=[{"role": "user", "content": "hi"}])
    host = FakeHost(episodes=[{"id": 9, "content": "model note", "keys": "other"}])
    _run(convo, host)
    # A model-made episode isn't our resume-state → create ours, don't clobber theirs.
    assert host.writes()[0][0] == "memory_remember"


def test_persist_skips_empty_session() -> None:
    host = FakeHost()
    _run(Conversation(), host)
    assert host.writes() == []


def test_resume_loads_session_summary() -> None:
    convo = Conversation()
    host = FakeHost(
        episodes=[
            {"id": 9, "content": "model note", "keys": "other"},
            {"id": 5, "content": "mine", "keys": "session-summary"},
        ]
    )
    asyncio.run(_resume_session(convo, host))  # type: ignore[arg-type]
    assert convo.summary == "mine"


def test_resume_no_session_is_noop() -> None:
    convo = Conversation()
    asyncio.run(_resume_session(convo, FakeHost(episodes=[])))  # type: ignore[arg-type]
    assert convo.summary == ""
