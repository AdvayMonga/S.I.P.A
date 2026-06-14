"""Scheduler store: task definitions in a vault note, last-run state in data/. No MCP here."""

import json
import os
import tempfile
from dataclasses import asdict, dataclass
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, cast
from uuid import uuid4

import frontmatter

NOTE_REL = "_system/Scheduled.md"
CADENCES = {"on-open", "daily", "weekly"}
_BODY = (
    "# Scheduled Tasks\n\n"
    "Managed by S.I.P.A. Edit `prompt`, `cadence` (on-open | daily | weekly), or `enabled` "
    "in the frontmatter above. Last-run times are tracked in `data/scheduler_state.json`.\n"
)


@dataclass
class Task:
    id: str
    prompt: str
    cadence: str
    enabled: bool = True


# --- definitions (vault note) -------------------------------------------------


def _note_path(vault_root: str | Path) -> Path:
    return Path(vault_root) / NOTE_REL


def load_tasks(vault_root: str | Path) -> list[Task]:
    path = _note_path(vault_root)
    if not path.is_file():
        return []
    raw = cast("list[dict[str, Any]]", frontmatter.load(str(path)).get("tasks") or [])
    return [
        Task(id=t["id"], prompt=t["prompt"], cadence=t["cadence"], enabled=t.get("enabled", True))
        for t in raw
    ]


def _write_tasks(vault_root: str | Path, tasks: list[Task]) -> None:
    path = _note_path(vault_root)
    path.parent.mkdir(parents=True, exist_ok=True)
    post = frontmatter.Post(_BODY, tasks=[asdict(t) for t in tasks])
    _atomic_write(path, frontmatter.dumps(post))


def add_task(vault_root: str | Path, prompt: str, cadence: str) -> Task:
    if cadence not in CADENCES:
        raise ValueError(f"cadence must be one of {sorted(CADENCES)}")
    tasks = load_tasks(vault_root)
    task = Task(id=uuid4().hex[:8], prompt=prompt, cadence=cadence)
    tasks.append(task)
    _write_tasks(vault_root, tasks)
    return task


def cancel_task(vault_root: str | Path, task_id: str) -> bool:
    tasks = load_tasks(vault_root)
    kept = [t for t in tasks if t.id != task_id]
    if len(kept) == len(tasks):
        return False
    _write_tasks(vault_root, kept)
    return True


# --- last-run state (data/) ---------------------------------------------------


def load_state(state_path: str | Path) -> dict[str, str]:
    path = Path(state_path)
    if not path.is_file():
        return {}
    return json.loads(path.read_text(encoding="utf-8"))


def mark_run(state_path: str | Path, task_id: str, now: datetime) -> None:
    state = load_state(state_path)
    state[task_id] = now.isoformat()
    path = Path(state_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    _atomic_write(path, json.dumps(state, indent=2))


# --- due logic ----------------------------------------------------------------


def is_due(task: Task, last_run_iso: str | None, now: datetime) -> bool:
    if not task.enabled:
        return False
    if task.cadence == "on-open" or last_run_iso is None:
        return True
    last = datetime.fromisoformat(last_run_iso)
    if task.cadence == "daily":
        return last.date() < now.date()
    if task.cadence == "weekly":
        return (now - last) >= timedelta(days=7)
    return False


def due_tasks(vault_root: str | Path, state_path: str | Path, now: datetime) -> list[Task]:
    state = load_state(state_path)
    return [t for t in load_tasks(vault_root) if is_due(t, state.get(t.id), now)]


def _atomic_write(target: Path, content: str) -> None:
    fd, tmp_name = tempfile.mkstemp(dir=target.parent, suffix=".tmp")
    tmp = Path(tmp_name)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            handle.write(content)
        os.replace(tmp, target)
    except BaseException:
        tmp.unlink(missing_ok=True)
        raise
