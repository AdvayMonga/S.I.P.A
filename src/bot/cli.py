"""REPL front-end: run any due scheduled tasks on open, then read-eval-print. No daemon yet."""

import asyncio
import json
import os
import sys

from mcp import StdioServerParameters

from .config import Settings
from .conversation import Conversation
from .host import MCPHost
from .loop import run_turn
from .provider import AnthropicProvider, ModelProvider


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


async def _run_due_tasks(
    convo: Conversation, provider: ModelProvider, host: MCPHost
) -> None:
    """On-open trigger: run each due scheduled task through a normal turn."""
    listing, _ = await host.call_tool("list_scheduled_tasks", {})
    due = [t for t in json.loads(listing) if t["due"]]
    if not due:
        return
    print(f"Running {len(due)} scheduled task(s)...")
    for task in due:
        print(f"[scheduled · {task['cadence']}] {task['prompt']}")
        reply = await run_turn(convo, task["prompt"], provider, host)
        print(f"sipa> {reply}")
        await host.call_tool("mark_task_ran", {"id": task["id"]})


async def _main() -> None:
    settings = Settings()  # type: ignore[call-arg]  # loaded from env / .env
    provider = AnthropicProvider(settings)
    async with MCPHost(_servers(settings)) as host:
        convo = Conversation()
        await _run_due_tasks(convo, provider, host)
        print("S.I.P.A. ready. Ctrl-D to exit.")
        while True:
            try:
                user = await asyncio.to_thread(input, "you> ")
            except EOFError:
                print()
                break
            if not user.strip():
                continue
            reply = await run_turn(convo, user, provider, host)
            print(f"sipa> {reply}")


def main() -> None:
    asyncio.run(_main())


if __name__ == "__main__":
    main()
