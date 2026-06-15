"""Event sources feed the daemon. Each `run(submit)` produces events and routes replies back to
their origin. Stdin (the REPL), a Unix socket (external clients), and a wall-clock timer."""

import asyncio
from collections.abc import Awaitable, Callable
from pathlib import Path

from .daemon import Submit


class ShutdownSignal(Exception):
    """Raised by the interactive source on EOF to bring the daemon down cleanly."""


class StdinSource:
    """The terminal REPL as an event source, so `make run` still gives an interactive prompt."""

    async def run(self, submit: Submit) -> None:
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
    """A Unix domain socket. Each connected client streams newline-delimited requests/replies."""

    def __init__(self, path: str) -> None:
        self._path = path

    async def run(self, submit: Submit) -> None:
        sock = Path(self._path)
        sock.parent.mkdir(parents=True, exist_ok=True)
        sock.unlink(missing_ok=True)  # clear a stale socket from a previous run
        server = await asyncio.start_unix_server(self._handler(submit), path=self._path)
        async with server:
            await server.serve_forever()

    def _handler(
        self, submit: Submit
    ) -> Callable[[asyncio.StreamReader, asyncio.StreamWriter], Awaitable[None]]:
        async def handle(reader: asyncio.StreamReader, writer: asyncio.StreamWriter) -> None:
            try:
                while True:
                    data = await reader.readline()
                    if not data:
                        break
                    text = data.decode().strip()
                    if not text:
                        continue
                    done = asyncio.Event()

                    async def respond(
                        reply: str,
                        writer: asyncio.StreamWriter = writer,
                        done: asyncio.Event = done,
                    ) -> None:
                        writer.write((reply + "\n").encode())
                        await writer.drain()
                        done.set()

                    await submit(text, respond)
                    await done.wait()
            finally:
                writer.close()

        return handle


class TimerSource:
    """Fires `on_tick` at startup (catch-up), then every `interval` seconds (wall-clock)."""

    def __init__(self, on_tick: Callable[[Submit], Awaitable[None]], interval: float) -> None:
        self._on_tick = on_tick
        self._interval = interval

    async def run(self, submit: Submit) -> None:
        while True:
            await self._on_tick(submit)
            await asyncio.sleep(self._interval)
