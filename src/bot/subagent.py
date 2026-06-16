"""Sub-agents: run isolated agent loops (fresh context, same tools, no further delegation) and fan
them out concurrently. The bot delegates independent sub-tasks; results come back as summaries.
See design/sub-agents.md."""

import asyncio
from collections.abc import Awaitable, Callable
from typing import Any

from .conversation import Conversation
from .host import MCPHost
from .provider import ModelProvider

MAX_SUBAGENTS = 5  # concurrency cap — keeps fan-out (and cost) in control

Notify = Callable[[int, str, str], Awaitable[None]]  # (id, task, result) -> deliver to the user

DELEGATE_TOOL: dict[str, Any] = {
    "name": "delegate",
    "description": (
        "Delegate independent sub-tasks to parallel sub-agents — each gets its own fresh "
        "context and the same tools, but cannot delegate further. Use ONLY for a big task that "
        "splits into genuinely independent parts (e.g. research several topics, review many "
        "files); do small or sequential work yourself. Returns each task's result, in order."
    ),
    "input_schema": {
        "type": "object",
        "properties": {
            "tasks": {
                "type": "array",
                "items": {"type": "string"},
                "description": "Independent, self-contained task prompts — one per sub-agent.",
            }
        },
        "required": ["tasks"],
    },
}


async def run_subagents(tasks: list[str], provider: ModelProvider, host: MCPHost) -> list[str]:
    """Run each task as an isolated sub-agent, concurrent up to MAX_SUBAGENTS; results in order."""
    from .loop import run_turn  # lazy: breaks the loop <-> subagent import cycle

    sem = asyncio.Semaphore(MAX_SUBAGENTS)

    async def one(task: str) -> str:
        async with sem:
            # Fresh conversation = isolated context; allow_delegate defaults False = no recursion.
            return await run_turn(Conversation(), task, provider, host)

    return list(await asyncio.gather(*(one(task) for task in tasks)))


DELEGATE_BACKGROUND_TOOL: dict[str, Any] = {
    "name": "delegate_background",
    "description": (
        "Start a long task in the BACKGROUND and return control immediately — use when the user "
        "asks for something lengthy (deep research, a big review) and may want to keep chatting "
        "meanwhile. Returns right away; the result is reported to the user when it finishes. Use "
        "this over `delegate` when the user shouldn't have to wait."
    ),
    "input_schema": {
        "type": "object",
        "properties": {"task": {"type": "string", "description": "The self-contained task."}},
        "required": ["task"],
    },
}


async def _default_notify(task_id: int, task: str, result: str) -> None:
    print(f"\n[✓ background #{task_id} done] {task}\n{result}\n")


class BackgroundDelegator:
    """Runs delegated tasks as detached background sub-agents (capped), delivering each result via
    `notify` when done — so the user keeps control while it runs. See design/sub-agents.md."""

    def __init__(
        self,
        provider: ModelProvider,
        host: MCPHost,
        notify: Notify = _default_notify,
        max_concurrent: int = MAX_SUBAGENTS,
    ) -> None:
        self._provider = provider
        self._host = host
        self._notify = notify
        self._sem = asyncio.Semaphore(max_concurrent)
        self._count = 0
        self._tasks: set[asyncio.Task[None]] = set()  # hold refs so tasks aren't GC'd mid-flight

    def set_notify(self, notify: Notify) -> None:
        """Replace how finished results are delivered (e.g. route through the event router)."""
        self._notify = notify

    async def start(self, task: str) -> str:
        """Kick off `task` in the background; return an ack immediately."""
        self._count += 1
        task_id = self._count
        runner = asyncio.create_task(self._run(task_id, task))
        self._tasks.add(runner)
        runner.add_done_callback(self._tasks.discard)
        return f"Started background task #{task_id}; I'll report the result when it's done."

    async def _run(self, task_id: int, task: str) -> None:
        from .loop import run_turn  # lazy: breaks the loop <-> subagent import cycle

        async with self._sem:
            try:
                result = await run_turn(Conversation(), task, self._provider, self._host)
            except Exception as exc:  # a failed background task must still report, not vanish
                result = f"[error] {exc}"
        await self._notify(task_id, task, result)
