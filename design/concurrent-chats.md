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
  Shown when `idle`/`ready`. Resolving a `running` thread = stop-then-resolve. The pool never goes
  empty: resolving your *last* thread spins up a fresh one (a clean chat is always available), and
  the desktop moves focus off the resolved thread to whatever remains.

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

## Fluid threads (M19): push delivery, hand-off, merge

M18 left one thing connection-bound: a turn's **reply comes back on the connection that sent the
message** (request/reply). That ties a reply to the thread you sent from, which fights moving live
work between threads. M19 decouples delivery so threads become fully fluid — you can peel a running
task off into its own thread mid-flight and merge it back when done.

### The model change: thread-tagged push delivery

Replies and approval prompts stop riding the send connection. Instead they flow over the existing
`:subscribe` push channel as **typed events tagged by thread id**:
- reply → `{topic: "reply", thread, text}`
- approval → `{topic: "approval", thread, id, question}`

Sending a message becomes **fire-and-forget**: the socket `send` submits the turn and returns an ack
immediately; the reply arrives later as a `reply` event tagged with whatever thread owns the task at
completion. The desktop is then a pure view — every thread's replies/approvals/status flow over one
channel, routed by `thread`. Proactive results (scheduled, background) are just `reply` events
tagged to the thread that ran them. (The old plain-line `sipa-push` is retired for replies.)

**Approval round-trip** moves to the daemon: a turn's `ask(question)` registers a pending future
keyed by a question id, pushes an `approval` event, and awaits the answer — delivered by a new
`:answer <id> <text>` verb (mirrors the desktop's existing approval registry, moved server-side).

### Pool concurrency rework (so a turn isn't bound to its origin thread)

Today `pool.submit` holds the thread's lock across the whole turn — which would pin a running turn
to its thread. M19 decouples them:
- A **`Turn`** = `{task, owner_id (mutable), start_len, convo}`. `owner_id` is where its reply lands;
  it can change (hand-off). `start_len` is the rollback point.
- A thread serializes its own turns via `current` + a small `pending` queue (not a held lock). A
  separate **driver** coroutine awaits the turn and, on completion, pushes the reply tagged by the
  turn's *current* `owner_id`, frees that owner, and starts its next pending message.

### Hand-off (mid-flight → background)

`background_thread(tid)` lifts `tid`'s running turn into a fresh thread B, **live, without restart**:
- B.convo = the turn's live convo (the object it's mutating); B.current = the turn; B running.
- A.convo = a copy of the convo's pre-turn prefix (`messages[:start_len]` + summary); A idle, free.
- turn.owner_id = B — so when it finishes, the reply lands in B.

A is instantly free to keep chatting (its conversation intact up to before the backgrounded task);
the task runs to completion in B; you **Merge** B back when ready. Copying the `[:start_len]` prefix
is safe — the running turn only appends past it.

### Merge

`merge_thread(source, target)` distills `source` (the `finalize_summary` machinery) into a findings
note, appends it into `target`'s convo so the next turn can use it, surfaces it in `target`'s
transcript, and drops `source` (frees the slot). Merge = Resolve whose distillation lands in a
thread's context instead of (just) memory.

### Backgrounding is user-driven only

Model-initiated `delegate_background` is **removed** — SIPA never backgrounds on its own. Fan-out
`delegate` (in-turn, synthesizes, one slot) stays. Backgrounding is a UI action: **→ background**
(hand-off) and **swap** (already built) are how parallelism happens, always your call.

### Build stages (M19) — ALL DONE (2026-06-18)

1. **Push delivery** ✓ — `Turn`(mutable `owner_id`)/driver pool rework; `reply` events tagged by
   thread (`pool.on_reply`, wired by the daemon); socket `:thread` path fire-and-forget (acks
   "queued"); legacy request/reply kept for REPL/sipa-client/timer; desktop routes replies by thread.
2. **Push approval** ✓ — `approval` events + daemon pending-answer registry (`_push_ask`/`answer`) +
   `:answer <id> <text>` verb + Rust `answer_approval`; approval card routed per thread.
3. **Remove model `delegate_background`** ✓ — `BackgroundDelegator` deleted; `delegate` fan-out kept.
4. **Hand-off** ✓ — `pool.background(tid)` (live, no restart) + `:background` verb + Rust
   `background_thread` + desktop "⤳ send to background" button (mirrors by moving the in-flight
   request from the source transcript to the new one).
5. **Merge** ✓ — `pool.merge(source, target)` (distill source → target's summary + a surfaced
   `reply` note, drop source) + `:merge` verb + Rust `merge_thread` + desktop "merge" button on
   non-focused slots (folds into the focused thread).

**As-built notes.** Reply/approval delivery is decoupled from the send connection: a turn delivers
**either** via push (`on_reply`, push clients) **or** via `respond` (legacy request/reply) — never
both. Approval prompts route through `pool.on_approval` and tag by the turn's **current** `owner_id`
(read at ask-time, not captured at turn-start), so an approval after a hand-off correctly shows on
the new thread. Merged findings land in the target's rolling `summary` (injected as "# Conversation
so far") rather than as a message, avoiding user/user alternation issues. Proactive pushes
(scheduled tasks) still ride the legacy plain-line path → main thread. GUI pass pending.

## Deferred (BACKLOG)

- Folding scheduled tasks & `delegate_background` into the thread pool (the grand unification).
- "Link two threads" for genuine shared context.
- Persisting open threads across daemon restarts (today only the resolved-episode memory survives).
- Per-thread cost/telemetry slicing.

## Build stages — ALL DONE (2026-06-17)

1. **ThreadPool backend** ✓ — `src/bot/pool.py`; daemon router → pool; serial-within/concurrent-
   across; `threads` telemetry.
2. **Thread-addressed socket protocol** ✓ — `:thread new` / `:thread <id>` (+ legacy default path).
3. **Roster awareness** ✓ — sibling `{label, status}` injected per turn in `run_turn`.
4. **Stop** ✓ — `:stop <id>`; cancelled turn rolled out of history; orphaned exec subprocess dies
   at its timeout (BACKLOG).
5. **Resolve** ✓ — `:resolve <id>`; thread distilled to its own memory episode, slot freed.
6. **Desktop switchboard** ✓ — Rust `ask(thread_id)` / `new_thread` / `stop_thread` /
   `resolve_thread`; `threads.tsx` (per-thread transcript/focus/unread, replies route post-swap);
   `Chat` shows the focused thread; `modules/Threads.tsx` is the panel (slots, swap, ready-light,
   Stop/Resolve, + new). Daemon broadcasts the snapshot on subscribe and on create.

**As-built notes.** Layout reuses the customizable tile grid (the "Background Agents" tile is now
the Threads switchboard — registry id kept as `"agents"` for saved-layout compatibility). Threads
are created dynamically up to 5 (a "+ new thread" button), not pre-rendered fixed slots. The desktop
derives `ready` (idle + unread + unfocused); the daemon only tracks running/idle. Proactive pushes
(background results, scheduled tasks) land on the main (lowest-id) thread. `delegate_background`'s
own `agents` telemetry is now UI-orphaned pending the pool unification (BACKLOG).
