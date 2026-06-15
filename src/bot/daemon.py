"""The always-on core: a single serialized turn-processor (the event router) fed by event sources.

One conversation, one queue — turns run one at a time, so sources (stdin, socket, timer) all feed
the same brain without racing. See design/daemon.md."""

import asyncio
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from typing import Protocol

Respond = Callable[[str], Awaitable[None]]
Submit = Callable[[str, Respond], Awaitable[None]]
Handler = Callable[[str], Awaitable[str]]


@dataclass
class Event:
    """An inbound request: text to process + how to deliver the reply to its origin."""

    text: str
    respond: Respond


class Source(Protocol):
    async def run(self, submit: Submit) -> None: ...


class Daemon:
    def __init__(self, handle: Handler) -> None:
        self._handle = handle
        self._queue: asyncio.Queue[Event] = asyncio.Queue()

    async def submit(self, text: str, respond: Respond) -> None:
        await self._queue.put(Event(text, respond))

    async def _router(self) -> None:
        while True:
            event = await self._queue.get()
            try:
                reply = await self._handle(event.text)
            except Exception as exc:  # one bad turn must never kill the daemon
                reply = f"[error] {exc}"
            await event.respond(reply)
            self._queue.task_done()

    async def run(self, sources: list[Source]) -> None:
        """Run the router and every source until one raises (e.g. stdin EOF → ShutdownSignal)."""
        async with asyncio.TaskGroup() as tg:
            tg.create_task(self._router())
            for source in sources:
                tg.create_task(source.run(self.submit))
