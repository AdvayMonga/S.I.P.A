"""Event sources feed the daemon. Each `run(submit, register)` produces request/reply events and
registers an output channel (sink) so the daemon can push proactive messages back. Stdin (REPL),
a Unix socket (clients; a `:subscribe` connection receives pushes), and a wall-clock timer."""

import asyncio
from collections.abc import Awaitable, Callable
from pathlib import Path

from .daemon import ASK_PREFIX, TELEMETRY_PREFIX, Daemon, Registrar, Respond, Submit
from .pool import PoolFull


class ShutdownSignal(Exception):
    """Raised by the interactive source on EOF to bring the daemon down cleanly."""


class StdinSource:
    """The terminal REPL as an event source, so `make run` still gives an interactive prompt."""

    async def run(self, submit: Submit, register: Registrar) -> None:
        async def sink(message: str) -> None:
            if message.startswith(TELEMETRY_PREFIX):
                return  # telemetry is for the dashboard, not the chat REPL
            print(f"\n[sipa] {message}")  # proactive message to the terminal

        register(sink)

        async def ask(question: str) -> str:
            print(f"sipa? {question}")
            return (await asyncio.to_thread(input, "approve> ")).strip()

        print("S.I.P.A. ready (daemon). Ctrl-D to exit.")
        while True:
            try:
                line = await asyncio.to_thread(input, "you> ")
            except EOFError:
                print()
                raise ShutdownSignal from None
            if not line.strip():
                continue
            done = asyncio.Event()

            async def respond(reply: str, done: asyncio.Event = done) -> None:
                print(f"sipa> {reply}")
                done.set()

            await submit(line, respond, ask)
            await done.wait()  # keep turns serial from this source


class SocketSource:
    """A Unix domain socket. The first line of a connection selects its mode:
    `:subscribe` → push channel; `:thread new` → create a thread (id returned) then chat on it;
    `:thread <id>` → chat on an existing thread; anything else → chat on the default thread."""

    def __init__(self, path: str, daemon: Daemon) -> None:
        self._path = path
        self._daemon = daemon  # thread management (create + addressed submit) lives on the daemon

    async def run(self, submit: Submit, register: Registrar) -> None:
        sock = Path(self._path)
        sock.parent.mkdir(parents=True, exist_ok=True)
        sock.unlink(missing_ok=True)  # clear a stale socket from a previous run

        async def handle(reader: asyncio.StreamReader, writer: asyncio.StreamWriter) -> None:
            try:
                first = await reader.readline()
                if not first:
                    return
                header = first.decode().strip()
                if header == ":subscribe":
                    await _subscribe(reader, writer, register)
                elif header == ":thread new":
                    await _serve_new_thread(self._daemon, reader, writer)
                elif header.startswith(":thread "):
                    tid = header[len(":thread ") :].strip()
                    await _serve_thread(self._daemon, tid, reader, writer)
                elif header.startswith(":stop "):
                    await self._daemon.stop(header[len(":stop ") :].strip())
                    await _send(writer, "ok")
                else:  # legacy: a plain message on the default thread (sipa-client)
                    await _converse(reader, writer, submit, first=first)
            finally:
                writer.close()

        server = await asyncio.start_unix_server(handle, path=self._path)
        async with server:
            await server.serve_forever()


async def _subscribe(
    reader: asyncio.StreamReader, writer: asyncio.StreamWriter, register: Registrar
) -> None:
    """Hold the connection open as a push channel until the client disconnects."""

    async def sink(message: str) -> None:
        writer.write((message + "\n").encode())
        await writer.drain()

    remove = register(sink)
    try:
        await reader.read()  # blocks until EOF (client disconnects)
    finally:
        remove()


async def _send(writer: asyncio.StreamWriter, text: str) -> bool:
    """Write a line to the client; swallow errors if it has disconnected (returns success)."""
    try:
        writer.write((text + "\n").encode())
        await writer.drain()
        return True
    except (ConnectionError, OSError):
        return False


Dispatch = Callable[[str, Respond, Callable[[str], Awaitable[str]]], Awaitable[None]]


async def _converse(
    reader: asyncio.StreamReader,
    writer: asyncio.StreamWriter,
    dispatch: Dispatch,
    first: bytes = b"",
) -> None:
    """Newline-delimited request/reply on one connection. `dispatch(text, respond, ask)` processes
    each message (default-thread `submit` or a thread-bound submit). Mid-turn questions go out with
    ASK_PREFIX; the client's next line is the answer."""

    async def ask(question: str) -> str:
        if not await _send(writer, ASK_PREFIX + question):
            return ""  # client gone → empty answer → treated as "not approved"
        answer = await reader.readline()
        return answer.decode().strip()

    line = first or await reader.readline()
    while line:
        text = line.decode().strip()
        if text:
            done = asyncio.Event()

            async def respond(reply: str, done: asyncio.Event = done) -> None:
                await _send(writer, reply)  # never raises into the pool if the client dropped
                done.set()

            await dispatch(text, respond, ask)
            await done.wait()
        line = await reader.readline()


async def _serve_thread(
    daemon: Daemon, tid: str, reader: asyncio.StreamReader, writer: asyncio.StreamWriter
) -> None:
    """Chat on a specific thread: every message routes to thread `tid`."""

    async def dispatch(text: str, respond: Respond, ask: Callable[[str], Awaitable[str]]) -> None:
        await daemon.submit_to(tid, text, respond, ask)

    await _converse(reader, writer, dispatch)


async def _serve_new_thread(
    daemon: Daemon, reader: asyncio.StreamReader, writer: asyncio.StreamWriter
) -> None:
    """Create a thread, send its id back as the first line, then chat on it."""
    try:
        tid = daemon.create_thread()
    except PoolFull as exc:
        await _send(writer, f"[error] {exc}")
        return
    await _send(writer, tid)
    await _serve_thread(daemon, tid, reader, writer)


class TimerSource:
    """Fires `on_tick` at startup (catch-up), then every `interval` seconds (wall-clock)."""

    def __init__(self, on_tick: Callable[[Submit], Awaitable[None]], interval: float) -> None:
        self._on_tick = on_tick
        self._interval = interval

    async def run(self, submit: Submit, register: Registrar) -> None:
        while True:
            await self._on_tick(submit)
            await asyncio.sleep(self._interval)
