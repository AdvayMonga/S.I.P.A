# design/scheduler.md

The scheduler — a persistent list of recurring tasks the bot runs proactively. Fills the
"task store + trigger" gap around `VISION.md` §5.2/§5.10. As-built.

## Two pieces, deliberately split

- **Store (a capability, the `scheduler` MCP server)** — *what* to do and *how often*. Owns the
  task list; the model adds/lists/cancels via tools. Never in core.
- **Trigger (the loop at startup, for now)** — *when* it fires. Reads due tasks via the host and
  runs them. A stand-in for the eventual timer source in the daemon; on-open only for now.

Core stays generic: it routes turns and (at startup) asks the scheduler what's due. Task content
is data in the store — adding a task is a tool call, never a core edit (invariant 5).

## Storage — split by who owns it

- **Definitions** → vault note `_system/Scheduled.md`, frontmatter `tasks:` list
  (`id`, `prompt`, `cadence`, `enabled`). Visible and editable in Obsidian, versioned by vault
  git. This is "the store you see." `_system/` is excluded from listing/search/index (like
  `_trash`) so it doesn't pollute knowledge results.
- **Last-run timestamps** → `data/scheduler_state.json` (gitignored, operational). Keeps the vault
  from churning every time a task runs; if lost, worst case a task runs once extra.

## Tools (`servers/scheduler/server.py`)

| Tool | Purpose |
|---|---|
| `schedule_task(prompt, cadence)` | add a task; `cadence` ∈ on-open / daily / weekly |
| `list_scheduled_tasks()` | JSON list with computed `due` status (for the trigger + the model) |
| `cancel_task(id)` | remove a task |
| `mark_task_ran(id)` | stamp last-run = now (called by the trigger after running a task) |

## Due logic (`store.is_due`)

- `on-open` → always due.
- `daily` → due if never run, or last-run date < today (local).
- `weekly` → due if never run, or ≥ 7 days since last run.
- `enabled: false` → never due.

`is_due` / `due_tasks` take an injected `now` for deterministic tests.

## Deferred (`BACKLOG.md`)

- **True timer firing** — unattended wall-clock schedule needs the daemon's timer source + event
  router. On-open is the M3 stand-in.
- **Shared `vault_git`** — the scheduler commits definition changes by importing
  `servers.obsidian.vault_git` (vault infra, not obsidian logic). Extract to a shared module.
