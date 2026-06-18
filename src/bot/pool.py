"""The thread pool — the switchboard. A flat pool of concurrent chat threads: each thread owns its
own Conversation and runs turns serially; threads run concurrently (up to MAX_THREADS). One turn at
a time per thread (its lock), many threads at once. See design/concurrent-chats.md."""

import asyncio
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any

from .conversation import Conversation

if TYPE_CHECKING:
    from .daemon import Ask, Respond

MAX_THREADS = 5  # flat-pool cap — up to 5 chats/tasks at once

# Runs one turn on a thread's conversation (given the sibling roster) -> the reply text.
ThreadHandler = Callable[[Conversation, str, "Ask | None", str], Awaitable[str]]
OnChange = Callable[[list[dict[str, Any]]], Awaitable[None]]  # broadcast the thread snapshot
Distill = Callable[[Conversation], Awaitable[None]]  # resolve -> persist to memory


class PoolFull(Exception):
    """Creating a thread would exceed MAX_THREADS."""


@dataclass
class Thread:
    """One chat thread: its own isolated context + lifecycle state."""

    id: str
    label: str
    convo: Conversation
    status: str = "idle"  # idle | running (the desktop derives "ready" from unread + focus)
    lock: asyncio.Lock = field(default_factory=asyncio.Lock)  # serial within the thread
    current: asyncio.Task[str] | None = None  # the in-flight turn, for stop()


class ThreadPool:
    """Holds the threads and runs their turns. `handle` runs one turn on a thread's conversation."""

    def __init__(self, handle: ThreadHandler, *, max_threads: int = MAX_THREADS) -> None:
        self._handle = handle
        self._max = max_threads
        self._threads: dict[str, Thread] = {}
        self._counter = 0
        self.on_change: OnChange | None = None  # set by cli → broadcast `threads` telemetry
        self.after_turn: Callable[[], Awaitable[None]] | None = None  # e.g. cost telemetry
        self.distill: Distill | None = None  # resolve → memory (wired in the Resolve stage)

    def create(self, label: str = "") -> str:
        if len(self._threads) >= self._max:
            raise PoolFull(f"thread pool full ({self._max})")
        self._counter += 1
        tid = str(self._counter)
        self._threads[tid] = Thread(id=tid, label=label, convo=Conversation())
        return tid

    def default_thread(self) -> str:
        """The lowest-numbered thread — the bridge target until the socket carries a thread id.
        Creates one if the pool is empty (e.g. after the last thread was resolved)."""
        return min(self._threads, key=int) if self._threads else self.create()

    def thread(self, tid: str) -> Thread:
        return self._threads[tid]

    def snapshot(self) -> list[dict[str, Any]]:
        return [{"id": t.id, "label": t.label, "status": t.status} for t in self._threads.values()]

    def _roster(self, tid: str) -> str:
        """The sibling threads' label + status — injected so a thread knows what else is running
        (not their contents). Roster awareness, per design/concurrent-chats.md."""
        return "\n".join(
            f'- "{t.label or "(new)"}" ({t.status})'
            for t in self._threads.values()
            if t.id != tid
        )

    async def _changed(self) -> None:
        if self.on_change is not None:
            await self.on_change(self.snapshot())

    async def submit(
        self, tid: str, text: str, respond: "Respond", ask: "Ask | None" = None
    ) -> None:
        """Run `text` as a turn on thread `tid`; deliver the reply via `respond`. Serial within the
        thread (its lock), concurrent across threads."""
        thread = self._threads.get(tid)
        if thread is None:
            await respond(f"[error] no such thread {tid}")
            return
        async with thread.lock:
            if not thread.label:
                thread.label = text[:40]
            thread.status = "running"
            await self._changed()
            roster = self._roster(tid)

            async def _run() -> str:
                return await self._handle(thread.convo, text, ask, roster)

            task = asyncio.create_task(_run())
            thread.current = task
            try:
                reply = await task
            except asyncio.CancelledError:
                if not task.cancelled():  # the submit itself was cancelled (shutdown) → propagate
                    raise
                reply = "[stopped]"  # stop() cancelled the turn
            except Exception as exc:  # one bad turn never kills the pool
                reply = f"[error] {exc}"
            finally:
                thread.current = None
                thread.status = "idle"
                await self._changed()
                if self.after_turn is not None:
                    try:
                        await self.after_turn()
                    except Exception:
                        pass
        await respond(reply)

    async def stop(self, tid: str) -> None:
        """Cancel a thread's in-flight turn (if any). The turn resolves to '[stopped]', idle."""
        thread = self._threads.get(tid)
        if thread is not None and thread.current is not None:
            thread.current.cancel()

    async def resolve(self, tid: str) -> None:
        """Close a thread: stop it, distill it to memory, remove it, free the slot."""
        thread = self._threads.pop(tid, None)
        if thread is None:
            return
        if thread.current is not None:
            thread.current.cancel()
        if self.distill is not None:
            try:
                await self.distill(thread.convo)
            except Exception:
                pass
        await self._changed()
