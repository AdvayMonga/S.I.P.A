"""Daemon front-end: build the host + conversation, wire event sources, run the always-on loop."""

import asyncio
import json
import logging
import os
import sys

from mcp import StdioServerParameters

from .config import Settings
from .conversation import Conversation, finalize_summary
from .daemon import Daemon, Handler, Submit
from .host import MCPHost
from .loop import run_turn
from .provider import ModelProvider, make_provider
from .sources import ShutdownSignal, SocketSource, StdinSource, TimerSource


def _servers(settings: Settings) -> dict[str, StdioServerParameters]:
    base_env = {
        "VAULT_PATH": str(settings.vault_path),
        "PATH": os.environ.get("PATH", ""),
    }
    return {
        "obsidian": StdioServerParameters(
            command=sys.executable,
            args=["-m", "servers.obsidian.server"],
            env={**base_env, "INDEX_PATH": str(settings.index_path.resolve())},
        ),
        "scheduler": StdioServerParameters(
            command=sys.executable,
            args=["-m", "servers.scheduler.server"],
            env={**base_env, "STATE_PATH": str(settings.scheduler_state_path.resolve())},
        ),
        "vault_search": StdioServerParameters(
            command=sys.executable,
            args=["-m", "servers.vault_search.server"],
            env={**base_env, "VSEARCH_DB": str(settings.vault_search_db_path.resolve())},
        ),
        "memory": StdioServerParameters(
            command=sys.executable,
            args=["-m", "servers.memory.server"],
            env={**base_env, "MEMORY_DB": str(settings.memory_db_path.resolve())},
        ),
    }


def _make_handler(convo: Conversation, provider: ModelProvider, host: MCPHost) -> Handler:
    """The turn-processor the router calls per event — one shared conversation, serialized."""

    async def handle(text: str) -> str:
        return await run_turn(convo, text, provider, host)

    return handle


def _make_fire_due(host: MCPHost):
    """Timer tick: submit each due scheduled task. on-open tasks fire only on the first (startup)
    tick — with a persistent daemon, 'open' means startup, not every wall-clock check."""
    first = True

    async def fire_due(submit: Submit) -> None:
        nonlocal first
        listing, _ = await host.call_tool("list_scheduled_tasks", {})
        for task in json.loads(listing):
            if not task["due"] or (task["cadence"] == "on-open" and not first):
                continue

            async def respond(reply: str, task: dict = task) -> None:
                await host.call_tool("mark_task_ran", {"id": task["id"]})
                print(f"[scheduled · {task['cadence']}] {reply}")

            await submit(task["prompt"], respond)
        first = False

    return fire_due


_SESSION_KEY = "session-summary"  # tags the single rolling resume-state episode


async def _session_episodes(host: MCPHost) -> list[dict]:
    """The active session-summary episode(s) — identified by key, ignoring model-made episodes."""
    listing, is_error = await host.call_tool("memory_list", {"kind": "episode"})
    if is_error:
        return []
    return [e for e in json.loads(listing) if e.get("keys") == _SESSION_KEY]


async def _resume_session(convo: Conversation, host: MCPHost) -> None:
    """Warm start: seed the rolling summary from the (single) session-summary episode."""
    sessions = await _session_episodes(host)
    if sessions:
        convo.summary = sessions[-1]["content"]
        print("resumed from last session.")


async def _persist_session(convo: Conversation, provider: ModelProvider, host: MCPHost) -> None:
    """On shutdown, distill the session — superseding the one session-summary entry, not piling up
    new episodes (each already folds the prior summary, so old ones are redundant)."""
    if not convo.messages:
        return
    try:
        summary = await finalize_summary(convo, provider)
        if not summary:
            return
        existing = await _session_episodes(host)
        if existing:
            await host.call_tool("memory_update", {"id": existing[-1]["id"], "content": summary})
        else:
            await host.call_tool(
                "memory_remember", {"content": summary, "kind": "episode", "keys": _SESSION_KEY}
            )
        print("session saved.")
    except Exception as exc:  # never let a bad save block exit
        print(f"[warn] could not save session: {exc}")


async def _main() -> None:
    logging.basicConfig(level=logging.WARNING, format="%(name)s: %(message)s")
    logging.getLogger("sipa.cost").setLevel(logging.INFO)
    settings = Settings()  # type: ignore[call-arg]  # loaded from env / .env
    provider = make_provider(settings)
    async with MCPHost(_servers(settings)) as host:
        convo = Conversation()
        await _resume_session(convo, host)
        daemon = Daemon(_make_handler(convo, provider, host))
        sources = [
            SocketSource(str(settings.socket_path.resolve())),
            TimerSource(_make_fire_due(host), settings.timer_interval),
            StdinSource(),
        ]
        try:
            await daemon.run(sources)
        except* ShutdownSignal:
            pass  # stdin EOF → clean exit
        await _persist_session(convo, provider, host)


def main() -> None:
    asyncio.run(_main())


if __name__ == "__main__":
    main()
