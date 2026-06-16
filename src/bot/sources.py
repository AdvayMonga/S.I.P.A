"""Event sources feed the daemon. Each `run(submit, register)` produces request/reply events and
registers an output channel (sink) so the daemon can push proactive messages back. Stdin (REPL),
a Unix socket (clients; a `:subscribe` connection receives pushes), and a wall-clock timer."""

import asyncio
from collections.abc import Awaitable, Callable
from pathlib import Path

from .daemon import Registrar, Submit


class ShutdownSignal(Exception):
    """Raised by the interactive source on EOF to bring the daemon down cleanly."""


class StdinSource:
    """The terminal REPL as an event source, so `make run` still gives an interactive prompt."""

    async def run(self, submit: Submit, register: Registrar) -> None:
        async def sink(message: str) -> None:
            print(f"\n[sipa] {message}")  # proactive message to the terminal

        register(sink)
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

            await submit(line, respond)
            await done.wait()  # keep turns serial from this source


class SocketSource:
    """A Unix domain socket. A connection that sends `:subscribe` first becomes a push channel
    (receives proactive messages); any other connection does newline-delimited request/reply."""

    def __init__(self, path: str) -> None:
        self._path = path

    async def run(self, submit: Submit, register: Registrar) -> None:
        sock = Path(self._path)
        sock.parent.mkdir(parents=True, exist_ok=True)
        sock.unlink(missing_ok=True)  # clear a stale socket from a previous run

        async def handle(reader: asyncio.StreamReader, writer: asyncio.StreamWriter) -> None:
            try:
                first = await reader.readline()
                if not first:
                    return
                if first.decode().strip() == ":subscribe":
                    await _subscribe(reader, writer, register)
                else:
                    await _serve(first, reader, writer, submit)
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


async def _serve(
    first: bytes, reader: asyncio.StreamReader, writer: asyncio.StreamWriter, submit: Submit
) -> None:
    """Newline-delimited request/reply on one connection (the first line is already read)."""
    line = first
    while line:
        text = line.decode().strip()
        if text:
            done = asyncio.Event()

            async def respond(reply: str, done: asyncio.Event = done) -> None:
                writer.write((reply + "\n").encode())
                await writer.drain()
                done.set()

            await submit(text, respond)
            await done.wait()
        line = await reader.readline()


class TimerSource:
    """Fires `on_tick` at startup (catch-up), then every `interval` seconds (wall-clock)."""

    def __init__(self, on_tick: Callable[[Submit], Awaitable[None]], interval: float) -> None:
        self._on_tick = on_tick
        self._interval = interval

    async def run(self, submit: Submit, register: Registrar) -> None:
        while True:
            await self._on_tick(submit)
            await asyncio.sleep(self._interval)
