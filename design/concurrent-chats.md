# design/concurrent-chats.md — the thread pool (the switchboard)

**Status: planned (M18).** Turns the daemon from one serial conversation into a **flat pool of
concurrent chat threads** you switch between — a switchboard. One thread is focused (shown in the
big chat module); the rest sit in the Background Agents panel as status boxes. Long work runs in
the background without disturbing the focused chat; results wait quietly in the panel until you
pull them in.

## Why

Today the daemon is serial-by-construction: one `Conversation`, one router, one turn at a time
(see `design/daemon.md`). A long turn (deep research, a fan-out) freezes everything behind it. The
user wants up to 5 things happening at once, the ability to keep chatting while work runs, and a
way to triage results without the main chat getting noisy. The switchboard delivers that without
fragmenting SIPA's "one assistant that knows me" identity — because **continuity lives in the
memory layer, not the conversation object** (M5/M6/M11). Threads are transient work surfaces; the
durable relationship is the shared memory every thread draws from.

## The model

A **flat pool** of up to `MAX_THREADS = 5` peer **threads**. No privileged "home" thread — every
thread is equal and resolvable; a fresh thread resumes warm from memory anyway, so the relationship
survives any thread's death.

A **Thread** = `{ id, label, status, Conversation }`:
- `id` — daemon-assigned, stable for the thread's life.
- `label` — short human tag (derived from the thread's first user message / task prompt), shown on
  the panel box.
- `status` — `idle | running` (see below).
- `Conversation` — the thread's own context (messages + rolling summary), isolated from siblings.

### Concurrency rules

1. **Serial within a thread.** A thread processes its own messages one at a time (its own queue).
   No races on its `Conversation`.
2. **Concurrent across threads.** Up to 5 threads can run turns simultaneously — that's the point.
3. **Isolated contexts.** A thread cannot read a sibling's conversation. Coherence per thread; no
   cross-thread races.

### State lifecycle

The daemon owns only two states: **`running`** (a turn is executing) and **`idle`** (not). The
third UI state, **`ready`** (finished with an unread result — the glowing light), is *derived by
the desktop*: `ready = idle && hasUnreadResult && !focused`. The daemon never tracks focus or
read/unread — that's pure UI state. Keeps the backend clean and the coupling minimal.

So: send a message → thread goes `running` → turn finishes → thread goes `idle`, desktop marks its
result unread → panel shows the `ready` light → you focus it (pull into the chat module) → desktop
clears unread → light off.

### Roster awareness (decided)

Threads are isolated on *contents* but aware of each other's *existence*. Each turn injects a small
roster into the thread's context — the sibling threads' `{label, status}` (we already broadcast
this as telemetry). So the focused thread can answer "what else are you working on?" with the gist,
without reading the others' transcripts. Durable knowledge still converges through memory on
resolve. (No live cross-thread transcript sharing — expensive and muddy; a "link two threads"
feature is a possible additive later.)

## Controls — Stop and Resolve (decided)

The panel becomes a real control panel (the "mini control panels" goal). Two distinct per-thread
actions:

- **Stop** — cancel a `running` turn (taking too long / changed your mind). Cancels the thread's
  in-flight turn task, which propagates `asyncio.CancelledError` through its tool calls and any
  fan-out sub-agents. The thread drops to `idle`; partial work is discarded. Shown when `running`.
- **Resolve** — close the thread: distill it to a memory episode (the per-thread M11 flow —
  `finalize_summary` → supersede/append episode), clear its context, remove it, free the slot.
  Shown when `idle`/`ready`. Resolving a `running` thread = stop-then-resolve.

**Cancellation (as-built).** Stop cancels the thread's turn task; `run_turn` catches
`CancelledError` and **rolls the stopped turn out of the conversation** (back to the pre-message
length) so no orphaned `tool_use` is left — the next turn on that thread stays alternation-valid.
Cancelling mid-`host.call_tool` is safe: the MCP session multiplexes by request id, so a late
response to the abandoned request is just dropped. The one imperfection: a `run_shell` subprocess in
the `exec` server keeps running until its own timeout cap (Stop is still prompt for the user). A
tighter kill-on-cancel needs cross-process MCP cancellation — deferred (`BACKLOG.md`).

## Backend changes

`daemon.py`'s single-`Conversation` router becomes a **`ThreadPool`**:

- `ThreadPool` holds `dict[str, Thread]` (cap `MAX_THREADS`). Each thread runs its own serial
  processing task; the pool runs them concurrently.
- `pool.create(label?) -> id` — new thread if under cap, else error.
- `pool.submit(id, text, respond, ask)` — route a message to thread `id`; serialized within the
  thread; runs `run_turn` on *that thread's* `Conversation`; `respond` delivers the reply.
- `pool.stop(id)` / `pool.resolve(id)` — the controls above.
- On every thread state change, broadcast the `threads` telemetry snapshot
  (`[{id, label, status}]`) — reuses the M17.x typed channel + the Background Agents tile machinery.

`run_turn` is unchanged in spirit — it already takes a `Conversation` and mutates it. It gains an
optional `roster` string injected into the system prompt. Stop is `task.cancel()` on the thread's
current turn task.

**Timer / scheduled tasks & `delegate_background`** fold naturally into threads later (a scheduled
fire or a delegated task = an auto-created thread that runs and goes `ready`) — but that
unification is **deferred** to keep M18 focused on the chat switchboard. For M18 they keep their
current behavior (broadcast / detached worker); migrating them onto the pool is a follow-up.

## Protocol changes

The Unix socket grows a small control grammar (first line of a connection):

- `:subscribe` — push channel (unchanged): chat pushes + `sipa-telemetry`.
- `:thread new` — create a thread; daemon replies with its `id`.
- `:thread <id>` — bind this connection to thread `<id>`; subsequent lines are messages, replies
  come back on this connection (request/reply, ASK_PREFIX approvals as today).
- `:stop <id>` / `:resolve <id>` — one-shot control verbs.

Desktop Tauri commands mirror these: existing `ask` gains a `thread_id`; new `new_thread`,
`stop_thread`, `resolve_thread` commands (same `invoke` seam as `ask`/`approve`).

## Desktop UI (the switchboard)

- **Chat module** shows the *focused* thread's transcript. Sending routes to that thread's id.
- **Background Agents panel** (rename → "Threads"/"Agents") shows a box per thread:
  `label`, a status dot (`running` pulses; `ready` glows; `idle` dim), and **Stop**/**Resolve**
  buttons per state. Always shows the pool's boxes.
- **Swap:** click a panel box → it becomes focused (its transcript loads into the chat module); the
  previously focused thread drops into the panel. Focus + unread tracked client-side.
- The desktop holds each thread's transcript locally (keyed by id), so swapping is instant and
  non-focused threads still receive their replies (the pending `ask` resolves into the right
  transcript whenever it completes).

## Deferred (BACKLOG)

- Folding scheduled tasks & `delegate_background` into the thread pool (the grand unification).
- "Link two threads" for genuine shared context.
- Persisting open threads across daemon restarts (today only the resolved-episode memory survives).
- Per-thread cost/telemetry slicing.

## Build stages (small commits, in order)

1. **ThreadPool backend** — `Thread` + `ThreadPool` (create/submit/stop/resolve, cap, per-thread
   serial, concurrent across); daemon routes stdin/socket to a default thread. `threads` telemetry.
   Tests. (No UI yet; behaviour-preserving for a single thread.)
2. **Thread-addressed socket protocol** — `:thread new` / `:thread <id>`; multi-thread messaging.
3. **Roster awareness** — inject sibling `{label, status}` into each turn.
4. **Stop** — cancel a thread's running turn (+ exec subprocess cancel hook).
5. **Resolve** — per-thread M11 distill + remove + free slot.
6. **Desktop switchboard** — focused chat + panel boxes + swap + ready-light + Stop/Resolve
   (several commits: protocol commands, thread-keyed transcript state, swap, controls).
