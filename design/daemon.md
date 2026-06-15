# design/daemon.md

The always-on core (VISION §10 "Daemon + agent core" + "Proactive triggers"). Turns the one-shot
REPL into a long-lived process: one brain (host + conversation), many event sources feeding it
through a single serialized router.

## Shape

```
sources ──submit(text, respond)──▶  Daemon queue  ──▶ router ──▶ run_turn ──▶ respond(reply)
  StdinSource    (the REPL)
  SocketSource   (Unix socket; external clients: desktop/Telegram later)
  TimerSource    (wall-clock; fires due scheduled tasks)
```

- **`Daemon`** (`daemon.py`) — holds a `handle: str -> str` (the turn-processor) and an
  `asyncio.Queue[Event]`. `_router` pulls events one at a time, runs `handle`, calls
  `event.respond(reply)`. Serial by construction → all sources share one `Conversation` without
  racing. A handler exception becomes an `[error] …` reply, never kills the daemon.
- **`Event`** = `text` + `respond` (an async callback that delivers the reply to *that event's
  origin* — the terminal, the socket client, or the scheduler).
- **`Source`** protocol = `run(submit)`. `run` is a long-lived producer; `submit(text, respond)`
  enqueues. Sources wait on their own `respond` (an `asyncio.Event`) so each keeps its turns serial.

## Sources (`sources.py`)

- **StdinSource** — the terminal REPL as a source, so `make run` is unchanged. EOF raises
  `ShutdownSignal`, which propagates through the TaskGroup and stops the daemon cleanly.
- **SocketSource** — `asyncio.start_unix_server` at `settings.socket_path` (`data/sipa.sock`).
  Newline-delimited request/reply per connection; clears a stale socket on start. `client.py`
  (`sipa-client`) is the reference client and the path the desktop/Telegram front-ends will reuse.
- **TimerSource** — fires `on_tick` immediately (startup catch-up) then every `timer_interval`
  seconds. `on_tick` = `_make_fire_due(host)`: lists scheduled tasks and submits the due ones.

## On-open semantics under a persistent process

`on-open` tasks are "always due" by design. With a daemon that never closes, that would re-fire them
every tick. So `_make_fire_due` carries a `first` flag: **on-open tasks fire only on the first
(startup) tick**; daily/weekly fire whenever genuinely due on any tick. `mark_task_ran` runs in the
task's `respond`, after the turn completes.

## Cost logging

`AnthropicProvider.generate` logs `tokens in/out` per call to the `sipa.cost` logger (INFO).
`cli` configures logging so it surfaces. Per-turn cost rollups / pricing are a later refinement.

## Scope boundary

- **Token budgeting** (VISION lists it with the daemon) — deferred. The char-budgeted context block
  (M6) is the only cap today; a real token budget pairs with the real tokenizer (`BACKLOG.md`).
- **Session-summary persistence across restarts** — now that a real session lifecycle exists, the
  M7 rolling summary could be persisted/distilled to a memory `episode` on shutdown. Deferred
  (`BACKLOG.md`) — keep M8 to process + transport + timer.
- **Telegram / webhook sources** — just more `Source`s; Telegram needs a bot token (asks the user).

## Done when

A multi-turn conversation runs through the daemon over the socket (via `sipa-client`), with token
usage logged; a due scheduled task fires on the wall-clock timer with no user input. `make check`
green with unit tests for the router (reply delivery, error isolation), the socket round-trip, and
the timer cadence.
