import asyncio
from types import SimpleNamespace
from typing import Any

from anthropic.types import TextBlock, ToolUseBlock

from bot.conversation import Conversation
from bot.loop import MAX_ITERATIONS, run_turn


class FakeHost:
    async def call_tool(self, name: str, arguments: dict) -> tuple[str, bool]:
        return ("", False)  # empty stores → base prompt; noop tool result

    def tools_for_model(self) -> list:
        return []


class LoopingProvider:
    """Never stops calling tools — simulates a runaway turn."""

    def __init__(self) -> None:
        self.calls = 0

    async def generate(self, *, system: str, messages: list, tools: list) -> Any:
        self.calls += 1
        block = ToolUseBlock(type="tool_use", id=f"t{self.calls}", name="noop", input={})
        return SimpleNamespace(content=[block], stop_reason="tool_use")


class OneShotProvider:
    async def generate(self, *, system: str, messages: list, tools: list) -> Any:
        return SimpleNamespace(
            content=[TextBlock(type="text", text="done")], stop_reason="end_turn"
        )


def test_runaway_turn_hits_hard_cap() -> None:
    convo = Conversation()
    provider = LoopingProvider()
    reply = asyncio.run(run_turn(convo, "go", provider, FakeHost()))  # type: ignore[arg-type]
    assert reply == f"[stopped after {MAX_ITERATIONS} tool iterations]"
    assert provider.calls == MAX_ITERATIONS  # stopped, not infinite
    assert convo.messages[-1]["role"] == "assistant"  # ends alternating, valid for next turn


def test_normal_turn_does_not_trip_cap() -> None:
    provider = OneShotProvider()
    reply = asyncio.run(run_turn(Conversation(), "hi", provider, FakeHost()))  # type: ignore[arg-type]
    assert reply == "done"
