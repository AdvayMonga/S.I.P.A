"""Daemon front-end: build the host + conversation, wire event sources, run the always-on loop."""

import asyncio
import json
import logging
import os
import sys

from mcp import StdioServerParameters

from .config import Settings
from .conversation import Conversation, finalize_summary
from .daemon import Ask, Daemon, Handler, Respond, Submit
from .host import MCPHost
from .loop import Approver, run_turn
from .provider import ModelProvider, make_provider
from .sources import ShutdownSignal, SocketSource, StdinSource, TimerSource
from .subagent import BackgroundDelegator


def _servers(settings: Settings) -> dict[str, StdioServerParameters]:
    base_env = {
        "VAULT_PATH": str(settings.vault_path),
        "PATH": os.environ.get("PATH", ""),
    }
    servers = {
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
    if settings.tavily_api_key:
        servers["web"] = StdioServerParameters(
            command=sys.executable,
            args=["-m", "servers.web.server"],
            env={**base_env, "TAVILY_API_KEY": settings.tavily_api_key},
        )
    if settings.fs_read_roots:
        servers["fs"] = StdioServerParameters(
            command=sys.executable,
            args=["-m", "servers.fs.server"],
            env={**base_env, "FS_READ_ROOTS": settings.fs_read_roots},
        )
    if settings.exec_root:
        servers["exec"] = StdioServerParameters(
            command=sys.executable,
            args=["-m", "servers.exec.server"],
            env={**base_env, "EXEC_ROOT": settings.exec_root},
        )
    return servers


def _make_handler(
    convo: Conversation,
    provider: ModelProvider,
    host: MCPHost,
    delegator: BackgroundDelegator,
    approver: Approver,
) -> Handler:
    """The turn-processor the router calls per event — one shared conversation, serialized."""

    async def handle(text: str, ask: Ask | None = None) -> str:
        return await run_turn(
            convo,
            text,
            provider,
            host,
            allow_delegate=True,
            spawn_background=delegator.start,
            ask=ask,
            approver=approver,
        )

    return handle


def _make_fire_due(host: MCPHost, notify: Respond):
    """Timer tick: submit each due scheduled task. on-open tasks fire only on the first (startup)
    tick — with a persistent daemon, 'open' means startup, not every wall-clock check. Output is
    broadcast (proactive), so it reaches every connected channel, not just the terminal."""
    first = True

    async def fire_due(submit: Submit) -> None:
        nonlocal first
        listing, _ = await host.call_tool("list_scheduled_tasks", {})
        for task in json.loads(listing):
            if not task["due"] or (task["cadence"] == "on-open" and not first):
                continue

            async def respond(reply: str, task: dict = task) -> None:
                await host.call_tool("mark_task_ran", {"id": task["id"]})
                await notify(f"[scheduled · {task['cadence']}] {reply}")

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
        delegator = BackgroundDelegator(provider, host)
        approver = Approver(settings.approval_mode)
        daemon = Daemon(_make_handler(convo, provider, host, delegator, approver))

        async def emit_cost() -> None:
            # After every turn, push running token/cost totals to the dashboard's Token Usage tile.
            await daemon.emit_telemetry("cost", provider.usage())

        daemon.after_turn = emit_cost

        async def present_background(task_id: int, task: str, result: str) -> None:
            # Route the finished result through the router so the bot presents it in context (lands
            # in the conversation) and `daemon.notify` broadcasts it to every connected channel.
            note = (
                f"[A background task you started just finished — #{task_id}: {task}]\n\n"
                f"Result:\n{result}\n\nTell the user it's done and the key takeaway, briefly."
            )
            await daemon.submit(note, daemon.notify)

        delegator.set_notify(present_background)
        sources = [
            SocketSource(str(settings.socket_path.resolve())),
            TimerSource(_make_fire_due(host, daemon.notify), settings.timer_interval),
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
