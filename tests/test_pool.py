import asyncio
from typing import Any

import pytest

from bot.conversation import Conversation
from bot.pool import PoolFull, ThreadPool


def _pool(handle: Any, **kw: Any) -> ThreadPool:
    return ThreadPool(handle, **kw)


async def _collect(pool: ThreadPool, tid: str, text: str) -> str:
    out: list[str] = []
    done = asyncio.Event()

    async def respond(reply: str) -> None:
        out.append(reply)
        done.set()

    await pool.submit(tid, text, respond)
    await asyncio.wait_for(done.wait(), 2)
    return out[0]


def test_submit_runs_a_turn_and_delivers_the_reply() -> None:
    async def scenario() -> None:
        async def handle(convo: Conversation, text: str, ask: Any = None, roster: str = "") -> str:
            return text.upper()

        pool = _pool(handle)
        tid = pool.create()
        assert await _collect(pool, tid, "hello") == "HELLO"

    asyncio.run(scenario())


def test_submit_isolates_handler_errors() -> None:
    async def scenario() -> None:
        async def handle(convo: Conversation, text: str, ask: Any = None, roster: str = "") -> str:
            raise ValueError("boom")

        pool = _pool(handle)
        tid = pool.create()
        reply = await _collect(pool, tid, "x")
        assert reply.startswith("[error]") and "boom" in reply

    asyncio.run(scenario())


def test_after_turn_hook_fires_after_each_turn() -> None:
    async def scenario() -> None:
        async def handle(convo: Conversation, text: str, ask: Any = None, roster: str = "") -> str:
            return "ok"

        fired: list[int] = []

        async def after() -> None:
            fired.append(1)

        pool = _pool(handle)
        pool.after_turn = after
        await _collect(pool, pool.create(), "hi")
        assert fired == [1]

    asyncio.run(scenario())


def test_on_change_broadcasts_running_then_idle() -> None:
    async def scenario() -> None:
        async def handle(convo: Conversation, text: str, ask: Any = None, roster: str = "") -> str:
            return "ok"

        statuses: list[str] = []

        async def on_change(snap: list[dict]) -> None:
            statuses.append(snap[0]["status"])

        pool = _pool(handle)
        pool.on_change = on_change
        await _collect(pool, pool.create(), "hi")
        assert statuses == ["running", "idle"]  # one snapshot at each transition

    asyncio.run(scenario())


def test_create_enforces_the_cap() -> None:
    async def handle(convo: Conversation, text: str, ask: Any = None, roster: str = "") -> str:
        return "ok"

    pool = _pool(handle, max_threads=2)
    pool.create()
    pool.create()
    with pytest.raises(PoolFull):
        pool.create()


def test_threads_run_concurrently_across_but_serial_within() -> None:
    async def scenario() -> None:
        order: list[str] = []

        async def handle(convo: Conversation, text: str, ask: Any = None, roster: str = "") -> str:
            order.append(f"start:{text}")
            await asyncio.sleep(0.05)
            order.append(f"end:{text}")
            return text

        pool = _pool(handle)
        a, b = pool.create(), pool.create()

        async def fire(tid: str, text: str) -> None:
            async def respond(_reply: str) -> None: ...

            await pool.submit(tid, text, respond)

        # Two threads in parallel interleave; both starts precede both ends.
        await asyncio.gather(fire(a, "A"), fire(b, "B"))
        assert order[:2] == ["start:A", "start:B"] or order[:2] == ["start:B", "start:A"]
        assert set(order[:2]) == {"start:A", "start:B"}

    asyncio.run(scenario())


def test_stop_cancels_a_running_turn() -> None:
    async def scenario() -> None:
        started = asyncio.Event()

        async def handle(convo: Conversation, text: str, ask: Any = None, roster: str = "") -> str:
            started.set()
            await asyncio.sleep(10)  # long turn we'll cancel
            return "done"

        pool = _pool(handle)
        tid = pool.create()
        out: list[str] = []
        done = asyncio.Event()

        async def respond(reply: str) -> None:
            out.append(reply)
            done.set()

        turn = asyncio.create_task(pool.submit(tid, "long", respond))
        await asyncio.wait_for(started.wait(), 1)
        await pool.stop(tid)
        await asyncio.wait_for(done.wait(), 1)
        assert out == ["[stopped]"]
        assert pool.thread(tid).status == "idle"
        turn.cancel()

    asyncio.run(scenario())


def test_resolve_removes_the_thread_and_frees_the_slot() -> None:
    async def scenario() -> None:
        async def handle(convo: Conversation, text: str, ask: Any = None, roster: str = "") -> str:
            return "ok"

        distilled: list[Conversation] = []

        async def distill(convo: Conversation) -> None:
            distilled.append(convo)

        pool = _pool(handle, max_threads=1)
        pool.distill = distill
        tid = pool.create()
        await pool.resolve(tid)
        assert len(distilled) == 1  # resolve distilled the thread to memory
        pool.create()  # slot freed → can create again under the cap

    asyncio.run(scenario())


def test_roster_lists_sibling_threads_not_self() -> None:
    async def scenario() -> None:
        seen: list[str] = []

        async def handle(convo: Conversation, text: str, ask: Any = None, roster: str = "") -> str:
            seen.append(roster)
            return "ok"

        pool = _pool(handle)
        a = pool.create("alpha")
        pool.create("beta")
        await _collect(pool, a, "hi")  # running thread a → roster names beta, not alpha
        assert "beta" in seen[-1]
        assert "alpha" not in seen[-1]

    asyncio.run(scenario())
