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


def _pool(handle: Any) -> ThreadPool:
    """Wrap a simple (text, ask) -> str handle into a ThreadPool for the daemon/socket tests."""

    async def h(convo: Conversation, text: str, ask: Any = None, roster: str = "") -> str:
        return await handle(text, ask)

    return ThreadPool(h)


async def _echo(text: str, ask: Any = None) -> str:
    return text


async def _no_scheduled() -> str:
    return "[]"


def _socket_task(sock: str, daemon: Daemon, scheduled: Any = _no_scheduled) -> "asyncio.Task[None]":
    src = SocketSource(sock, daemon, scheduled)
    return asyncio.create_task(src.run(daemon.submit, daemon.register_sink))


async def _read_topic(reader: asyncio.StreamReader, topic: str) -> dict:
    """Read telemetry lines until one with the given topic; return its payload."""
    while True:
        line = await asyncio.wait_for(reader.readline(), 1)
        if not line:
            raise AssertionError(f"connection closed before topic {topic!r}")
        text = line.decode()
        if text.startswith(TELEMETRY_PREFIX):
            payload = json.loads(text[len(TELEMETRY_PREFIX) :])
            if payload.get("topic") == topic:
                return payload


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


def test_snapshot_returns_threads_and_scheduled() -> None:
    # The unified initial-state fetch: one JSON object with both slow-changing modules' state.
    sock = f"/tmp/sipa_snap_{os.getpid()}.sock"

    async def scenario() -> None:
        daemon = Daemon(_pool(_echo))
        daemon.create_thread("main")

        async def scheduled() -> str:
            return json.dumps([{"id": "abc", "prompt": "stand-up", "cadence": "daily"}])

        source = _socket_task(sock, daemon, scheduled)
        await asyncio.sleep(0.05)

        reader, writer = await asyncio.open_unix_connection(sock)
        writer.write(b":snapshot\n")
        await writer.drain()
        snap = json.loads((await asyncio.wait_for(reader.readline(), 1)).decode())
        writer.close()

        assert [t["label"] for t in snap["threads"]] == ["main"]
        assert snap["scheduled"][0]["prompt"] == "stand-up"
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
        handle = _make_handle(provider, fhost, Approver())  # type: ignore[arg-type]
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
        first = await asyncio.wait_for(reader.readline(), 1)  # threads snapshot sent on subscribe
        assert first.decode().startswith(TELEMETRY_PREFIX)
        await daemon.notify("background done")
        line = await asyncio.wait_for(reader.readline(), 1)
        assert line.decode().strip() == "background done"
        writer.close()
        source.cancel()

    try:
        asyncio.run(scenario())
    finally:
        Path(sock).unlink(missing_ok=True)


def test_thread_new_routes_and_pushes_reply() -> None:
    sock = f"/tmp/sipa_tnew_{os.getpid()}.sock"

    async def scenario() -> None:
        async def handle(text: str, ask: Any = None) -> str:
            return f"echo:{text}"

        pool = _pool(handle)
        daemon = Daemon(pool)
        source = _socket_task(sock, daemon)
        await asyncio.sleep(0.05)

        # A subscribe connection receives the pushed reply (fire-and-forget send).
        sreader, swriter = await asyncio.open_unix_connection(sock)
        swriter.write(b":subscribe\n")
        await swriter.drain()

        reader, writer = await asyncio.open_unix_connection(sock)
        writer.write(b":thread new\n")  # create a thread; first reply line is its id
        await writer.drain()
        tid = (await asyncio.wait_for(reader.readline(), 1)).decode().strip()
        writer.write(b"hi\n")  # fire-and-forget; daemon acks "queued"
        await writer.drain()
        assert (await asyncio.wait_for(reader.readline(), 1)).decode().strip() == "queued"

        reply = await _read_topic(sreader, "reply")  # reply pushed, tagged by thread
        assert reply["thread"] == tid
        assert reply["text"] == "echo:hi"
        writer.close()
        swriter.close()
        source.cancel()

    try:
        asyncio.run(scenario())
    finally:
        Path(sock).unlink(missing_ok=True)


def test_thread_approval_pushes_and_answers() -> None:
    sock = f"/tmp/sipa_appr_{os.getpid()}.sock"

    async def scenario() -> None:
        async def handle(text: str, ask: Any = None) -> str:
            ans = await ask(f"confirm {text}")  # mid-turn approval over the push channel
            return f"did:{text}:{ans}"

        daemon = Daemon(_pool(handle))
        source = _socket_task(sock, daemon)
        await asyncio.sleep(0.05)

        sreader, swriter = await asyncio.open_unix_connection(sock)
        swriter.write(b":subscribe\n")
        await swriter.drain()

        reader, writer = await asyncio.open_unix_connection(sock)
        writer.write(b":thread new\n")
        await writer.drain()
        await asyncio.wait_for(reader.readline(), 1)  # the id
        writer.write(b"delete X\n")
        await writer.drain()

        appr = await _read_topic(sreader, "approval")  # approval pushed, tagged by thread
        assert "confirm delete X" in appr["question"]
        areader, awriter = await asyncio.open_unix_connection(sock)  # answer via :answer
        awriter.write(f":answer {appr['id']} yes\n".encode())
        await awriter.drain()

        reply = await _read_topic(sreader, "reply")
        assert reply["text"] == "did:delete X:yes"
        writer.close()
        swriter.close()
        awriter.close()
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

        sreader, swriter = await asyncio.open_unix_connection(sock)
        swriter.write(b":subscribe\n")
        await swriter.drain()

        reader, writer = await asyncio.open_unix_connection(sock)
        writer.write(f":thread {tid}\nyo\n".encode())  # bind to the existing thread + send
        await writer.drain()
        reply = await _read_topic(sreader, "reply")
        assert reply["thread"] == tid
        assert reply["text"] == "echo:yo"
        writer.close()
        swriter.close()
        source.cancel()

    try:
        asyncio.run(scenario())
    finally:
        Path(sock).unlink(missing_ok=True)
