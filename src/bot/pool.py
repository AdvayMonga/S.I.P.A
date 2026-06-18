"""The thread pool — the switchboard. A flat pool of concurrent chat threads: each thread owns its
own Conversation and runs turns serially; threads run concurrently (up to MAX_THREADS).

Turns are decoupled from their origin thread (a `Turn` with a mutable `owner_id`) so a running turn
can be handed off to another thread mid-flight; its reply lands wherever it's owned at completion.
A driver coroutine (not a held lock) awaits each turn and delivers. See design/concurrent-chats."""

import asyncio
from collections import deque
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
OnReply = Callable[[str, str], Awaitable[None]]  # push a turn's reply, tagged by thread id
OnApproval = Callable[[str, str], Awaitable[str]]  # (thread id, question) -> the user's answer
Distill = Callable[[Conversation], Awaitable[None]]  # resolve -> persist to memory
Summarize = Callable[[Conversation], Awaitable[str]]  # merge -> distill a thread to a findings note


class PoolFull(Exception):
    """Creating a thread would exceed MAX_THREADS."""


@dataclass
class Turn:
    """One in-flight turn. `owner_id` is where its reply *and* its mid-turn approvals are tagged —
    mutable, so a hand-off re-tags both. `respond` is the legacy request/reply sink (else None)."""

    owner_id: str
    start_len: int  # convo length before this turn — the rollback point on stop/hand-off
    convo: Conversation
    respond: "Respond | None" = None
    task: asyncio.Task[str] | None = None  # set right after construction in _start


@dataclass
class Thread:
    """One chat thread: its own isolated context + lifecycle state."""

    id: str
    label: str
    convo: Conversation
    status: str = "idle"  # idle | running (the desktop derives "ready" from unread + focus)
    current: Turn | None = None  # the in-flight turn, if any
    pending: "deque[tuple[str, Ask | None, Respond | None]]" = field(default_factory=deque)


class ThreadPool:
    """Holds the threads and runs their turns. `handle` runs one turn on a thread's conversation."""

    def __init__(self, handle: ThreadHandler, *, max_threads: int = MAX_THREADS) -> None:
        self._handle = handle
        self._max = max_threads
        self._threads: dict[str, Thread] = {}
        self._counter = 0
        self.on_change: OnChange | None = None  # broadcast `threads` telemetry on state change
        self.on_reply: OnReply | None = None  # push a reply tagged by thread (decoupled delivery)
        self.on_approval: OnApproval | None = None  # ask the user (push, tagged by current owner)
        self.after_turn: Callable[[], Awaitable[None]] | None = None  # e.g. cost telemetry
        self.distill: Distill | None = None  # resolve → memory
        self.summarize: Summarize | None = None  # merge → distill a thread to a findings note

    def create(self, label: str = "") -> str:
        if len(self._threads) >= self._max:
            raise PoolFull(f"thread pool full ({self._max})")
        self._counter += 1
        tid = str(self._counter)
        self._threads[tid] = Thread(id=tid, label=label, convo=Conversation())
        return tid

    def default_thread(self) -> str:
        """The lowest-numbered thread — the bridge target for non-addressed sources.
        Creates one if the pool is empty (e.g. after the last thread was resolved)."""
        return min(self._threads, key=int) if self._threads else self.create()

    def thread(self, tid: str) -> Thread:
        return self._threads[tid]

    def snapshot(self) -> list[dict[str, Any]]:
        return [{"id": t.id, "label": t.label, "status": t.status} for t in self._threads.values()]

    def _roster(self, tid: str) -> str:
        """The sibling threads' label + status — injected so a thread knows what else is running."""
        return "\n".join(
            f'- "{t.label or "(new)"}" ({t.status})'
            for t in self._threads.values()
            if t.id != tid
        )

    async def _changed(self) -> None:
        if self.on_change is not None:
            await self.on_change(self.snapshot())

    async def submit(
        self, tid: str, text: str, ask: "Ask | None" = None, respond: "Respond | None" = None
    ) -> None:
        """Queue `text` on thread `tid`. Serial within the thread (one turn at a time, the rest wait
        in `pending`); concurrent across threads. The reply is pushed via `on_reply` (tagged by the
        owning thread) and, if `respond` is given, delivered there too (legacy request/reply)."""
        thread = self._threads.get(tid)
        if thread is None:
            if respond is not None:
                await respond(f"[error] no such thread {tid}")
            return
        if not thread.label:
            thread.label = text[:40]
        if thread.current is not None:  # busy → queue (serial within the thread)
            thread.pending.append((text, ask, respond))
            return
        await self._start(thread, text, ask, respond)

    async def _start(
        self, thread: Thread, text: str, ask: "Ask | None", respond: "Respond | None"
    ) -> None:
        start_len = len(thread.convo.messages)
        roster = self._roster(thread.id)
        convo = thread.convo
        turn = Turn(thread.id, start_len, convo, respond)
        # Push clients pass no ask: build one that tags approvals by the turn's *current* owner, so
        # a mid-flight hand-off re-routes the approval to the new thread, not the one it started on.
        if ask is None and (on_approval := self.on_approval) is not None:

            async def push_ask(question: str) -> str:
                return await on_approval(turn.owner_id, question)

            ask = push_ask

        async def _run() -> str:
            return await self._handle(convo, text, ask, roster)

        turn.task = asyncio.create_task(_run())
        thread.current = turn
        thread.status = "running"
        await self._changed()
        asyncio.create_task(self._drive(turn))

    async def _drive(self, turn: Turn) -> None:
        """Await a turn and deliver its reply to whoever owns it at completion (the owner may have
        changed via hand-off). Mark that owner idle first (so waiters see consistent state), deliver
        the reply, then start its next queued message."""
        assert turn.task is not None  # set in _start before the driver is spawned
        try:
            reply = await turn.task
        except asyncio.CancelledError:
            if not turn.task.cancelled():  # the driver itself was cancelled (shutdown) → propagate
                raise
            reply = "[stopped]"
        except Exception as exc:  # one bad turn never kills the pool
            reply = f"[error] {exc}"
        owner = self._threads.get(turn.owner_id)
        if owner is not None and owner.current is turn:
            owner.current = None
            owner.status = "idle"
            await self._changed()
        # One delivery path: legacy request/reply if a respond was given (REPL, sipa-client, timer),
        # else push tagged by the owning thread (desktop) — so no double-delivery.
        if turn.respond is not None:
            try:
                await turn.respond(reply)
            except Exception:
                pass
        elif self.on_reply is not None:
            await self.on_reply(turn.owner_id, reply)
        if self.after_turn is not None:
            try:
                await self.after_turn()
            except Exception:
                pass
        if owner is not None and owner.pending and owner.current is None:
            text, ask, respond = owner.pending.popleft()
            await self._start(owner, text, ask, respond)

    @staticmethod
    def _task_label(turn: Turn) -> str:
        """The user message that started this turn (for naming a handed-off thread), if present."""
        msgs = turn.convo.messages
        if turn.start_len < len(msgs) and isinstance(msgs[turn.start_len], dict):
            return str(msgs[turn.start_len].get("content", ""))[:40]
        return ""

    async def background(self, tid: str) -> str | None:
        """Hand a thread's running turn off to a fresh thread, live (no restart). The new thread
        takes the running turn + its conversation; the source rolls back to before this turn and
        goes idle. Returns the new thread's id, or None if nothing was running."""
        src = self._threads.get(tid)
        if src is None or src.current is None:
            return None
        turn = src.current
        bid = self.create()  # may raise PoolFull
        b = self._threads[bid]
        b.label = self._task_label(turn) or src.label  # name B after the task it's running
        b.convo = turn.convo  # the live object the turn is mutating
        b.current = turn
        b.status = "running"
        turn.owner_id = bid  # its reply now lands in B
        src.convo = Conversation(
            messages=list(turn.convo.messages[: turn.start_len]),  # pre-turn prefix only
            summary=turn.convo.summary,
        )
        src.current = None
        src.status = "idle"
        await self._changed()
        if src.pending:
            text, ask, respond = src.pending.popleft()
            await self._start(src, text, ask, respond)
        return bid

    @staticmethod
    def _cancel(turn: Turn | None) -> None:
        if turn is not None and turn.task is not None:
            turn.task.cancel()

    async def stop(self, tid: str) -> None:
        """Cancel a thread's in-flight turn (if any). The turn resolves to '[stopped]', idle."""
        thread = self._threads.get(tid)
        if thread is not None:
            self._cancel(thread.current)

    async def merge(self, source_tid: str, target_tid: str) -> None:
        """Fold a thread's findings into another: distill the source into a note, inject it into the
        target's context (its rolling summary), surface it in the target's transcript, then drop the
        source. Merge = Resolve whose distillation lands in a thread, not memory."""
        source = self._threads.get(source_tid)
        target = self._threads.get(target_tid)
        if source is None or target is None or source_tid == target_tid:
            return
        self._cancel(source.current)
        findings = ""
        if self.summarize is not None:
            try:
                findings = await self.summarize(source.convo)
            except Exception:
                findings = ""
        if findings:
            note = f'[Merged from a side task "{source.label}"]\n{findings}'
            target.convo.summary = f"{target.convo.summary}\n\n{note}".strip()
            if self.on_reply is not None:
                await self.on_reply(target_tid, note)  # surface it in the target's transcript
        self._threads.pop(source_tid, None)
        await self._changed()

    async def resolve(self, tid: str) -> None:
        """Close a thread: stop it, distill it to memory, remove it, free the slot."""
        thread = self._threads.pop(tid, None)
        if thread is None:
            return
        self._cancel(thread.current)
        if self.distill is not None:
            try:
                await self.distill(thread.convo)
            except Exception:
                pass
        await self._changed()
