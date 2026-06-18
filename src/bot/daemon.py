"""The always-on core: the push channel (proactive output sinks + telemetry) and the bridge from
event sources to the thread pool. Turns run in the pool now — serial within a thread, concurrent
across threads — so a long turn no longer freezes the others. The daemon wires sources to the pool
and broadcasts proactive messages. See design/daemon.md + design/concurrent-chats.md."""

import asyncio
import json
from collections.abc import Awaitable, Callable
from typing import TYPE_CHECKING, Any, Protocol

if TYPE_CHECKING:
    from .pool import ThreadPool

ASK_PREFIX = "\x01?"  # a socket line starting with this is a question, not a reply (clients prompt)
TELEMETRY_PREFIX = "\x01T"  # a pushed line with this prefix is a telemetry snapshot (JSON)

Respond = Callable[[str], Awaitable[None]]
Ask = Callable[[str], Awaitable[str]]  # ask the user a question mid-turn; await their answer
Sink = Callable[[str], Awaitable[None]]  # delivers a proactive message to one output channel
Registrar = Callable[[Sink], Callable[[], None]]  # register a sink → returns its unregister fn


class Submit(Protocol):
    async def __call__(self, text: str, respond: Respond, ask: Ask | None = None) -> None: ...


class Source(Protocol):
    async def run(self, submit: Submit, register: Registrar) -> None: ...


class Daemon:
    """The push channel + source→pool bridge. Holds the thread pool; `submit` routes a source's
    message to the pool's default thread (per-thread addressing comes with the socket protocol)."""

    def __init__(self, pool: "ThreadPool") -> None:
        self._pool = pool
        self._sinks: set[Sink] = set()  # connected output channels for proactive messages

    async def submit(self, text: str, respond: Respond, ask: Ask | None = None) -> None:
        await self._pool.submit(self._pool.default_thread(), text, respond, ask)

    def create_thread(self, label: str = "") -> str:
        """Create a new chat thread (raises PoolFull past the cap) — the socket's `:thread new`."""
        return self._pool.create(label)

    async def submit_to(
        self, tid: str, text: str, respond: Respond, ask: Ask | None = None
    ) -> None:
        """Route a message to a specific thread — the socket's `:thread <id>` path."""
        await self._pool.submit(tid, text, respond, ask)

    async def stop(self, tid: str) -> None:
        """Cancel a thread's in-flight turn — the socket's `:stop <id>`."""
        await self._pool.stop(tid)

    async def resolve(self, tid: str) -> None:
        """Close a thread (distill to memory, free the slot) — the socket's `:resolve <id>`."""
        await self._pool.resolve(tid)

    def register_sink(self, sink: Sink) -> Callable[[], None]:
        """A source registers an output channel; returns a fn to unregister it on disconnect."""
        self._sinks.add(sink)
        return lambda: self._sinks.discard(sink)

    async def notify(self, message: str) -> None:
        """Push an unsolicited message to every connected channel (terminal + socket subscribers).
        This is the proactive-delivery primitive: background results, scheduled tasks, reminders."""
        for sink in list(self._sinks):
            try:
                await sink(message)
            except Exception:  # a dead client must not block delivery to the others
                pass

    async def emit_telemetry(self, topic: str, payload: dict[str, Any]) -> None:
        """Broadcast a typed state snapshot for one module (cost, agents, threads …) over the same
        push channel as chat — the desktop routes on the prefix + topic. See design/dashboard.md."""
        await self.notify(TELEMETRY_PREFIX + json.dumps({"topic": topic, **payload}))

    async def broadcast_threads(self) -> None:
        """Push the current thread snapshot — called when a client subscribes so its switchboard
        populates immediately (the pool otherwise only broadcasts on a state change)."""
        await self.emit_telemetry("threads", {"threads": self._pool.snapshot()})

    async def run(self, sources: list[Source]) -> None:
        """Run every source until one raises (e.g. stdin EOF → ShutdownSignal). Turns themselves run
        in the pool, spawned per-submit — no central router task."""
        async with asyncio.TaskGroup() as tg:
            for source in sources:
                tg.create_task(source.run(self.submit, self.register_sink))
