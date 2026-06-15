import asyncio
import os
from pathlib import Path
from types import SimpleNamespace
from typing import Any

from anthropic.types import TextBlock

from bot.cli import _make_handler
from bot.conversation import Conversation
from bot.daemon import Daemon
from bot.sources import SocketSource, TimerSource


def test_router_delivers_reply() -> None:
    async def scenario() -> None:
        async def handle(text: str) -> str:
            return text.upper()

        daemon = Daemon(handle)
        router = asyncio.create_task(daemon._router())
        out: list[str] = []
        done = asyncio.Event()

        async def respond(reply: str) -> None:
            out.append(reply)
            done.set()

        await daemon.submit("hello", respond)
        await asyncio.wait_for(done.wait(), 1)
        router.cancel()
        assert out == ["HELLO"]

    asyncio.run(scenario())


def test_router_isolates_handler_errors() -> None:
    async def scenario() -> None:
        async def handle(text: str) -> str:
            raise ValueError("boom")

        daemon = Daemon(handle)
        router = asyncio.create_task(daemon._router())
        out: list[str] = []
        done = asyncio.Event()

        async def respond(reply: str) -> None:
            out.append(reply)
            done.set()

        await daemon.submit("x", respond)
        await asyncio.wait_for(done.wait(), 1)
        # The daemon survives and turns the failure into a reply.
        assert not router.done()
        router.cancel()
        assert out[0].startswith("[error]") and "boom" in out[0]

    asyncio.run(scenario())


def test_socket_round_trip() -> None:
    # AF_UNIX paths are ~104 chars max; pytest's tmp_path is too deep, so use a short /tmp path.
    sock = f"/tmp/sipa_test_{os.getpid()}.sock"

    async def scenario() -> None:
        async def handle(text: str) -> str:
            return f"echo:{text}"

        daemon = Daemon(handle)
        router = asyncio.create_task(daemon._router())
        source = asyncio.create_task(SocketSource(sock).run(daemon.submit))
        await asyncio.sleep(0.05)  # let the server bind

        reader, writer = await asyncio.open_unix_connection(sock)
        writer.write(b"hi\n")
        await writer.drain()
        line1 = await asyncio.wait_for(reader.readline(), 1)
        writer.write(b"again\n")  # same connection, multi-turn
        await writer.drain()
        line2 = await asyncio.wait_for(reader.readline(), 1)
        writer.close()

        assert line1.decode().strip() == "echo:hi"
        assert line2.decode().strip() == "echo:again"
        router.cancel()
        source.cancel()

    try:
        asyncio.run(scenario())
    finally:
        Path(sock).unlink(missing_ok=True)


class _FakeProvider:
    async def generate(self, *, system: str, messages: list, tools: list) -> Any:
        return SimpleNamespace(
            content=[TextBlock(type="text", text="pong")], stop_reason="end_turn"
        )


class _FakeHost:
    """Empty stores → assemble_context degrades to the base prompt; no tools."""

    async def call_tool(self, name: str, arguments: dict) -> tuple[str, bool]:
        return ("", False) if name == "memory_get_profile" else ("[]", False)

    def tools_for_model(self) -> list:
        return []


def test_real_handler_wiring_over_socket() -> None:
    # Exercises cli._make_handler → run_turn → context assembly end to end (fakes, no API).
    sock = f"/tmp/sipa_wiring_{os.getpid()}.sock"

    async def scenario() -> None:
        handle = _make_handler(Conversation(), _FakeProvider(), _FakeHost())  # type: ignore[arg-type]
        daemon = Daemon(handle)
        router = asyncio.create_task(daemon._router())
        source = asyncio.create_task(SocketSource(sock).run(daemon.submit))
        await asyncio.sleep(0.05)

        reader, writer = await asyncio.open_unix_connection(sock)
        writer.write(b"hi there\n")
        await writer.drain()
        line = await asyncio.wait_for(reader.readline(), 1)
        writer.close()
        assert line.decode().strip() == "pong"
        router.cancel()
        source.cancel()

    try:
        asyncio.run(scenario())
    finally:
        Path(sock).unlink(missing_ok=True)


def test_timer_fires_repeatedly() -> None:
    async def scenario() -> None:
        ticks = 0

        async def on_tick(submit) -> None:
            nonlocal ticks
            ticks += 1

        source = asyncio.create_task(TimerSource(on_tick, interval=0.02).run(submit=None))  # type: ignore[arg-type]
        await asyncio.sleep(0.1)
        source.cancel()
        assert ticks >= 3  # fired at startup + on the interval

    asyncio.run(scenario())
