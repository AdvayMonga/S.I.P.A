import asyncio
from types import SimpleNamespace
from typing import Any

from anthropic.types import TextBlock, ToolUseBlock

from bot.conversation import Conversation
from bot.loop import MAX_ITERATIONS, Approver, run_turn


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


def test_approval_denied_when_unattended() -> None:
    # No interactive session (ask is None) → approval-gated tools are denied (the unattended-block).
    assert asyncio.run(Approver().approve("run_shell", {"command": "ls"}, None)) is False


def test_approval_follows_user_answer() -> None:
    async def yes(_q: str) -> str:
        return "y"

    async def no(_q: str) -> str:
        return "nope"

    assert asyncio.run(Approver().approve("run_shell", {"command": "ls"}, yes)) is True
    assert asyncio.run(Approver().approve("run_shell", {"command": "rm -rf /"}, no)) is False


def test_trust_mode_runs_without_asking() -> None:
    asked = False

    async def ask(_q: str) -> str:
        nonlocal asked
        asked = True
        return "n"

    ok = asyncio.run(Approver(mode="trust").approve("run_shell", {"command": "ls"}, ask))
    assert ok is True and asked is False  # never prompted


def test_always_allowlists_the_command() -> None:
    async def scenario() -> None:
        prompts = 0

        async def ask(_q: str) -> str:
            nonlocal prompts
            prompts += 1
            return "always"

        approver = Approver()
        assert await approver.approve("run_shell", {"command": "npm test"}, ask) is True
        # same command again — allowlisted, no second prompt
        assert await approver.approve("run_shell", {"command": "npm test"}, ask) is True
        # a different command still prompts
        assert await approver.approve("run_shell", {"command": "npm run build"}, ask) is True
        assert prompts == 2

    asyncio.run(scenario())
