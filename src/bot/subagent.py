"""Sub-agents: run isolated agent loops (fresh context, same tools, no further delegation) and fan
them out concurrently. The bot delegates independent sub-tasks; results come back as summaries.
See design/sub-agents.md."""

import asyncio
from typing import Any

from .conversation import Conversation
from .host import MCPHost
from .provider import ModelProvider

MAX_SUBAGENTS = 5  # concurrency cap — keeps fan-out (and cost) in control

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
