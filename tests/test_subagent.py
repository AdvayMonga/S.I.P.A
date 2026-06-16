import asyncio
from types import SimpleNamespace
from typing import Any

from anthropic.types import TextBlock, ToolUseBlock

from bot.conversation import Conversation
from bot.loop import run_turn
from bot.subagent import BackgroundDelegator, run_subagents


class FakeHost:
    """Empty stores → assemble_context degrades to the base prompt; no tools."""

    async def call_tool(self, name: str, arguments: dict) -> tuple[str, bool]:
        return ("", False) if name == "memory_get_profile" else ("[]", False)

    def tools_for_model(self) -> list:
        return []


class EchoProvider:
    """A sub-agent that finishes immediately, echoing its task."""

    async def generate(self, *, system: str, messages: list, tools: list) -> Any:
        last = messages[-1]["content"]
        text = f"done: {last}" if isinstance(last, str) else "done"
        return SimpleNamespace(content=[TextBlock(type="text", text=text)], stop_reason="end_turn")


def test_run_subagents_fans_out() -> None:
    out = asyncio.run(run_subagents(["a", "b", "c"], EchoProvider(), FakeHost()))  # type: ignore[arg-type]
    assert out == ["done: a", "done: b", "done: c"]


def test_run_subagents_handles_more_than_the_cap() -> None:
    tasks = [str(i) for i in range(8)]  # > MAX_SUBAGENTS; all still complete, in order
    out = asyncio.run(run_subagents(tasks, EchoProvider(), FakeHost()))  # type: ignore[arg-type]
    assert out == [f"done: {i}" for i in range(8)]


class DelegatingProvider:
    """Main turn delegates two sub-tasks, then finishes; sub-agents finish immediately."""

    def __init__(self) -> None:
        self.subagent_calls = 0

    async def generate(self, *, system: str, messages: list, tools: list) -> Any:
        has_delegate = any(t.get("name") == "delegate" for t in tools)
        last = messages[-1]["content"]
        if has_delegate and isinstance(last, str):  # top-level user turn → delegate
            block = ToolUseBlock(
                type="tool_use", id="d1", name="delegate", input={"tasks": ["x", "y"]}
            )
            return SimpleNamespace(content=[block], stop_reason="tool_use")
        if not has_delegate:  # a sub-agent turn
            self.subagent_calls += 1
        return SimpleNamespace(content=[TextBlock(type="text", text="ok")], stop_reason="end_turn")


def test_delegate_runs_subagents_through_run_turn() -> None:
    provider = DelegatingProvider()
    reply = asyncio.run(
        run_turn(Conversation(), "big task", provider, FakeHost(), allow_delegate=True)  # type: ignore[arg-type]
    )
    assert reply == "ok"
    assert provider.subagent_calls == 2  # both sub-agents ran (x, y)


def test_sub_agents_cannot_delegate() -> None:
    # Sub-agents run with allow_delegate=False → no delegate tool offered to them.
    seen: list[bool] = []

    class Recorder:
        async def generate(self, *, system: str, messages: list, tools: list) -> Any:
            seen.append(any(t.get("name") == "delegate" for t in tools))
            return SimpleNamespace(
                content=[TextBlock(type="text", text="x")], stop_reason="end_turn"
            )

    asyncio.run(run_subagents(["t"], Recorder(), FakeHost()))  # type: ignore[arg-type]
    assert seen == [False]


def test_background_delegator_returns_immediately_then_notifies() -> None:
    async def scenario() -> None:
        delivered: list[tuple[int, str, str]] = []

        async def notify(task_id: int, task: str, result: str) -> None:
            delivered.append((task_id, task, result))

        d = BackgroundDelegator(EchoProvider(), FakeHost(), notify=notify)  # type: ignore[arg-type]
        ack = await d.start("research X")
        assert "#1" in ack  # returned right away with an ack — not the result
        assert delivered == []  # result hasn't arrived yet
        await asyncio.gather(*d._tasks)  # wait for the detached worker
        assert delivered == [(1, "research X", "done: research X")]

    asyncio.run(scenario())


def test_background_delegate_path_through_run_turn() -> None:
    started: list[str] = []

    async def spawn(task: str) -> str:
        started.append(task)
        return f"started: {task}"

    class BgProvider:
        async def generate(self, *, system: str, messages: list, tools: list) -> Any:
            last = messages[-1]["content"]
            if isinstance(last, str):  # top-level user turn → delegate in background
                block = ToolUseBlock(
                    type="tool_use",
                    id="b1",
                    name="delegate_background",
                    input={"task": "deep dive"},
                )
                return SimpleNamespace(content=[block], stop_reason="tool_use")
            return SimpleNamespace(
                content=[TextBlock(type="text", text="on it")], stop_reason="end"
            )

    reply = asyncio.run(
        run_turn(
            Conversation(),
            "do a deep dive",
            BgProvider(),  # type: ignore[arg-type]
            FakeHost(),  # type: ignore[arg-type]
            allow_delegate=True,
            spawn_background=spawn,
        )
    )
    assert reply == "on it"
    assert started == ["deep dive"]  # the background task was kicked off
