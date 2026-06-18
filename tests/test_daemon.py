import asyncio
import json
import os
from pathlib import Path
from types import SimpleNamespace
from typing import Any

from anthropic.types import TextBlock

from bot.cli import _make_handle
from bot.conversation import Conversation
from bot.daemon import ASK_PREFIX, TELEMETRY_PREFIX, Daemon
from bot.loop import Approver
from bot.pool import ThreadPool
from bot.sources import SocketSource, TimerSource
from bot.subagent import BackgroundDelegator


def _pool(handle: Any) -> ThreadPool:
    """Wrap a simple (text, ask) -> str handle into a ThreadPool for the daemon/socket tests."""

    async def h(convo: Conversation, text: str, ask: Any = None, roster: str = "") -> str:
        return await handle(text, ask)

    return ThreadPool(h)


async def _echo(text: str, ask: Any = None) -> str:
    return text


def _socket_task(sock: str, daemon: Daemon) -> "asyncio.Task[None]":
    return asyncio.create_task(SocketSource(sock, daemon).run(daemon.submit, daemon.register_sink))


def test_socket_round_trip() -> None:
    # AF_UNIX paths are ~104 chars max; pytest's tmp_path is too deep, so use a short /tmp path.
    sock = f"/tmp/sipa_test_{os.getpid()}.sock"

    async def scenario() -> None:
        async def handle(text: str, ask: Any = None) -> str:
            return f"echo:{text}"

        daemon = Daemon(_pool(handle))
        source = _socket_task(sock, daemon)
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

    def usage(self) -> dict:
        return {}


class _FakeHost:
    """Empty stores → assemble_context degrades to the base prompt; no tools."""

    async def call_tool(self, name: str, arguments: dict) -> tuple[str, bool]:
        return ("", False) if name == "memory_get_profile" else ("[]", False)

    def tools_for_model(self) -> list:
        return []


def test_real_handler_wiring_over_socket() -> None:
    # Exercises cli._make_handle → pool → run_turn → context assembly end to end (fakes, no API).
    sock = f"/tmp/sipa_wiring_{os.getpid()}.sock"

    async def scenario() -> None:
        provider, fhost = _FakeProvider(), _FakeHost()
        delegator = BackgroundDelegator(provider, fhost)  # type: ignore[arg-type]
        handle = _make_handle(provider, fhost, delegator, Approver())  # type: ignore[arg-type]
        daemon = Daemon(ThreadPool(handle))
        source = _socket_task(sock, daemon)
        await asyncio.sleep(0.05)

        reader, writer = await asyncio.open_unix_connection(sock)
        writer.write(b"hi there\n")
        await writer.drain()
        line = await asyncio.wait_for(reader.readline(), 1)
        writer.close()
        assert line.decode().strip() == "pong"
        source.cancel()

    try:
        asyncio.run(scenario())
    finally:
        Path(sock).unlink(missing_ok=True)


def test_socket_ask_round_trip() -> None:
    # A turn asks the user mid-flight; the answer comes back over the same connection.
    sock = f"/tmp/sipa_ask_{os.getpid()}.sock"

    async def scenario() -> None:
        async def handle(text: str, ask: Any = None) -> str:
            answer = await ask(f"confirm {text}")  # mid-turn question
            return f"did:{text}:{answer}"

        daemon = Daemon(_pool(handle))
        source = _socket_task(sock, daemon)
        await asyncio.sleep(0.05)

        reader, writer = await asyncio.open_unix_connection(sock)
        writer.write(b"delete X\n")
        await writer.drain()
        question = await asyncio.wait_for(reader.readline(), 1)
        assert question.decode().startswith(ASK_PREFIX)  # marked as a question
        assert "confirm delete X" in question.decode()
        writer.write(b"yes\n")  # the answer
        await writer.drain()
        reply = await asyncio.wait_for(reader.readline(), 1)
        assert reply.decode().strip() == "did:delete X:yes"
        writer.close()
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

        source = asyncio.create_task(
            TimerSource(on_tick, interval=0.02).run(None, _noreg)  # type: ignore[arg-type]
        )
        await asyncio.sleep(0.1)
        source.cancel()
        assert ticks >= 3  # fired at startup + on the interval

    asyncio.run(scenario())


def _noreg(_sink: Any) -> Any:
    return lambda: None


def test_notify_broadcasts_to_registered_sinks() -> None:
    async def scenario() -> None:
        daemon = Daemon(_pool(_echo))
        got_a: list[str] = []
        got_b: list[str] = []

        async def sink_a(msg: str) -> None:
            got_a.append(msg)

        async def sink_b(msg: str) -> None:
            got_b.append(msg)

        remove_a = daemon.register_sink(sink_a)
        daemon.register_sink(sink_b)
        await daemon.notify("ping")
        remove_a()  # unregister A
        await daemon.notify("pong")
        assert got_a == ["ping"]  # A only saw the first
        assert got_b == ["ping", "pong"]  # B saw both

    asyncio.run(scenario())


def test_emit_telemetry_is_a_typed_envelope() -> None:
    async def scenario() -> None:
        daemon = Daemon(_pool(_echo))
        got: list[str] = []

        async def sink(msg: str) -> None:
            got.append(msg)

        daemon.register_sink(sink)
        await daemon.emit_telemetry("cost", {"cost_usd": 0.5, "in_tokens": 10})
        assert len(got) == 1
        assert got[0].startswith(TELEMETRY_PREFIX)
        payload = json.loads(got[0][len(TELEMETRY_PREFIX) :])
        assert payload == {"topic": "cost", "cost_usd": 0.5, "in_tokens": 10}

    asyncio.run(scenario())


def test_subscribe_connection_receives_pushes() -> None:
    sock = f"/tmp/sipa_sub_{os.getpid()}.sock"

    async def scenario() -> None:
        daemon = Daemon(_pool(_echo))
        source = _socket_task(sock, daemon)
        await asyncio.sleep(0.05)

        reader, writer = await asyncio.open_unix_connection(sock)
        writer.write(b":subscribe\n")  # become a push channel
        await writer.drain()
        await asyncio.sleep(0.05)  # let the subscribe register its sink
        await daemon.notify("background done")
        line = await asyncio.wait_for(reader.readline(), 1)
        assert line.decode().strip() == "background done"
        writer.close()
        source.cancel()

    try:
        asyncio.run(scenario())
    finally:
        Path(sock).unlink(missing_ok=True)


def test_thread_new_creates_and_routes() -> None:
    sock = f"/tmp/sipa_tnew_{os.getpid()}.sock"

    async def scenario() -> None:
        async def handle(text: str, ask: Any = None) -> str:
            return f"echo:{text}"

        pool = _pool(handle)
        daemon = Daemon(pool)
        source = _socket_task(sock, daemon)
        await asyncio.sleep(0.05)

        reader, writer = await asyncio.open_unix_connection(sock)
        writer.write(b":thread new\n")  # create a thread; first reply line is its id
        await writer.drain()
        tid = (await asyncio.wait_for(reader.readline(), 1)).decode().strip()
        assert tid in {t["id"] for t in pool.snapshot()}  # thread exists in the pool
        writer.write(b"hi\n")  # a message on that thread
        await writer.drain()
        reply = await asyncio.wait_for(reader.readline(), 1)
        assert reply.decode().strip() == "echo:hi"
        writer.close()
        source.cancel()

    try:
        asyncio.run(scenario())
    finally:
        Path(sock).unlink(missing_ok=True)


def test_resolve_verb_closes_the_thread() -> None:
    sock = f"/tmp/sipa_resolve_{os.getpid()}.sock"

    async def scenario() -> None:
        pool = _pool(_echo)
        daemon = Daemon(pool)
        tid = pool.create("doomed")
        source = _socket_task(sock, daemon)
        await asyncio.sleep(0.05)

        reader, writer = await asyncio.open_unix_connection(sock)
        writer.write(f":resolve {tid}\n".encode())
        await writer.drain()
        ack = await asyncio.wait_for(reader.readline(), 1)
        assert ack.decode().strip() == "ok"
        assert tid not in {t["id"] for t in pool.snapshot()}  # gone, slot freed
        writer.close()
        source.cancel()

    try:
        asyncio.run(scenario())
    finally:
        Path(sock).unlink(missing_ok=True)


def test_thread_bound_routes_to_existing() -> None:
    sock = f"/tmp/sipa_tbound_{os.getpid()}.sock"

    async def scenario() -> None:
        async def handle(text: str, ask: Any = None) -> str:
            return f"echo:{text}"

        pool = _pool(handle)
        daemon = Daemon(pool)
        tid = pool.create("preexisting")
        source = _socket_task(sock, daemon)
        await asyncio.sleep(0.05)

        reader, writer = await asyncio.open_unix_connection(sock)
        writer.write(f":thread {tid}\n".encode())  # bind to the existing thread
        await writer.drain()
        writer.write(b"yo\n")
        await writer.drain()
        reply = await asyncio.wait_for(reader.readline(), 1)
        assert reply.decode().strip() == "echo:yo"
        writer.close()
        source.cancel()

    try:
        asyncio.run(scenario())
    finally:
        Path(sock).unlink(missing_ok=True)
