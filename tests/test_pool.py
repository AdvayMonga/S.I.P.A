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

    await pool.submit(tid, text, respond=respond)
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


def test_push_delivery_when_no_respond() -> None:
    async def scenario() -> None:
        async def handle(convo: Conversation, text: str, ask: Any = None, roster: str = "") -> str:
            return text.upper()

        pushed: list[tuple[str, str]] = []
        done = asyncio.Event()

        async def on_reply(tid: str, text: str) -> None:
            pushed.append((tid, text))
            done.set()

        pool = _pool(handle)
        pool.on_reply = on_reply
        tid = pool.create()
        await pool.submit(tid, "hello")  # no respond → reply is pushed, tagged by thread
        await asyncio.wait_for(done.wait(), 2)
        assert pushed == [(tid, "HELLO")]

    asyncio.run(scenario())


def test_serial_within_thread() -> None:
    async def scenario() -> None:
        order: list[str] = []

        async def handle(convo: Conversation, text: str, ask: Any = None, roster: str = "") -> str:
            order.append(f"start:{text}")
            await asyncio.sleep(0.03)
            order.append(f"end:{text}")
            return text

        replies: list[str] = []
        done = asyncio.Event()

        async def respond(reply: str) -> None:
            replies.append(reply)
            if len(replies) == 2:
                done.set()

        pool = _pool(handle)
        tid = pool.create()
        await pool.submit(tid, "first", respond=respond)
        await pool.submit(tid, "second", respond=respond)  # queued behind first (same thread)
        await asyncio.wait_for(done.wait(), 2)
        assert order == ["start:first", "end:first", "start:second", "end:second"]

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
        done = asyncio.Event()
        finished: list[str] = []

        async def respond(reply: str) -> None:
            finished.append(reply)
            if len(finished) == 2:
                done.set()

        await pool.submit(a, "A", respond=respond)  # fire-and-forget; turns run concurrently
        await pool.submit(b, "B", respond=respond)
        await asyncio.wait_for(done.wait(), 2)
        # Both threads ran at once: both starts precede both ends.
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

        await pool.submit(tid, "long", respond=respond)
        await asyncio.wait_for(started.wait(), 1)
        await pool.stop(tid)
        await asyncio.wait_for(done.wait(), 1)
        assert out == ["[stopped]"]
        assert pool.thread(tid).status == "idle"

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


def test_background_hands_off_running_turn_without_restart() -> None:
    async def scenario() -> None:
        started = asyncio.Event()
        release = asyncio.Event()
        runs: list[str] = []

        async def handle(convo: Conversation, text: str, ask: Any = None, roster: str = "") -> str:
            runs.append(text)
            started.set()
            await release.wait()  # hold the turn open so we can hand it off mid-flight
            return f"done:{text}"

        pushed: list[tuple[str, str]] = []
        done = asyncio.Event()

        async def on_reply(tid: str, text: str) -> None:
            pushed.append((tid, text))
            done.set()

        pool = _pool(handle)
        pool.on_reply = on_reply
        a = pool.create("a")
        await pool.submit(a, "research")  # push client (no respond)
        await asyncio.wait_for(started.wait(), 1)

        bid = await pool.background(a)  # hand the running turn to a new thread
        assert bid is not None and bid != a
        assert pool.thread(a).status == "idle"  # source freed immediately
        assert pool.thread(a).current is None
        assert pool.thread(bid).status == "running"  # turn continues in B

        release.set()
        await asyncio.wait_for(done.wait(), 1)
        assert runs == ["research"]  # ran once — no restart
        assert pushed == [(bid, "done:research")]  # reply landed in B, not A

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
