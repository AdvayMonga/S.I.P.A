"""Daemon front-end: build the host + conversation, wire event sources, run the always-on loop."""

import asyncio
import json
import logging
import os
import sys

from mcp import StdioServerParameters

from .config import Settings
from .conversation import Conversation
from .daemon import Daemon, Handler, Submit
from .host import MCPHost
from .loop import run_turn
from .provider import AnthropicProvider
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


def _make_handler(convo: Conversation, provider: AnthropicProvider, host: MCPHost) -> Handler:
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


async def _main() -> None:
    logging.basicConfig(level=logging.WARNING, format="%(name)s: %(message)s")
    logging.getLogger("sipa.cost").setLevel(logging.INFO)
    settings = Settings()  # type: ignore[call-arg]  # loaded from env / .env
    provider = AnthropicProvider(settings)
    async with MCPHost(_servers(settings)) as host:
        daemon = Daemon(_make_handler(Conversation(), provider, host))
        sources = [
            SocketSource(str(settings.socket_path.resolve())),
            TimerSource(_make_fire_due(host), settings.timer_interval),
            StdinSource(),
        ]
        try:
            await daemon.run(sources)
        except* ShutdownSignal:
            pass  # stdin EOF → clean exit


def main() -> None:
    asyncio.run(_main())


if __name__ == "__main__":
    main()
