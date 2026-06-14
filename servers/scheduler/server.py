"""Scheduler MCP server: recurring-task CRUD over stdio. Definition changes are git-committed."""

import json
import os
from datetime import datetime

from mcp.server.fastmcp import FastMCP

from servers.obsidian import vault_git  # shared vault git infra (see BACKLOG: extract to shared)
from servers.scheduler import store

mcp = FastMCP("scheduler")


def _vault() -> str:
    return os.environ["VAULT_PATH"]


def _state() -> str:
    return os.environ["STATE_PATH"]


@mcp.tool()
def schedule_task(prompt: str, cadence: str) -> str:
    """Schedule a recurring task. cadence is one of: on-open, daily, weekly."""
    task = store.add_task(_vault(), prompt, cadence)
    vault_git.commit(_vault(), f"schedule: add {task.id} ({cadence})")
    return f"Scheduled [{task.id}] ({cadence}): {prompt}"


@mcp.tool()
def list_scheduled_tasks() -> str:
    """List scheduled tasks as JSON, each with its computed `due` status as of now."""
    now = datetime.now()
    state = store.load_state(_state())
    rows = [
        {
            "id": task.id,
            "prompt": task.prompt,
            "cadence": task.cadence,
            "enabled": task.enabled,
            "last_run": state.get(task.id),
            "due": store.is_due(task, state.get(task.id), now),
        }
        for task in store.load_tasks(_vault())
    ]
    return json.dumps(rows)


@mcp.tool()
def cancel_task(id: str) -> str:
    """Remove a scheduled task by id."""
    if not store.cancel_task(_vault(), id):
        return f"No such task: {id}"
    vault_git.commit(_vault(), f"schedule: cancel {id}")
    return f"Cancelled {id}"


@mcp.tool()
def mark_task_ran(id: str) -> str:
    """Stamp a task's last-run time = now (called by the on-open trigger after running it)."""
    store.mark_run(_state(), id, datetime.now())
    return f"Marked {id} run"


if __name__ == "__main__":
    mcp.run()
