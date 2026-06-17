# PLAN.md

The work queue. Near-term scope only; empties as work finishes. North-star specs are
`VISION.md` (the bot) and `siloop.md` (the loop) — this file holds what's *next*, not the whole
destination.

---

## Current milestone — M0: thin vertical slice

**Status (2026-06-13): DONE.** Live turn verified end to end — Claude Opus 4.8 → MCP host →
obsidian server → real vault (`~/Desktop/CORE`): the bot created a note and committed it to the
vault's git as a clean, separately-attributed commit. All five components built; `make check`
green. M0 complete.

**Goal.** One real end-to-end path: type a message in a terminal → the bot calls Claude → it
writes a note into the real Obsidian vault. Proves the loop, the provider, and one store
mutation work together against real data. Everything else in `VISION.md` graduates from here.

**Deliberately NOT in M0** (each deferred to its own milestone in `VISION.md` §10): daemon,
socket, MCP host / subprocess servers, event router, token budgeting, cost accounting, semantic
search, memory store, desktop app, Telegram. No premature infrastructure.

**Scope — build in this order:**

1. **config** — typed Settings: `ANTHROPIC_API_KEY`, `VAULT_PATH`. Load from env, fail fast if
   missing.
2. **provider** — minimal `ModelProvider` interface + `AnthropicProvider` (messages + tools →
   response + usage). Keep the interface even with one impl; it's cheap and it's the seam the
   local model swaps into later (`VISION.md` §5.4).
3. **obsidian MCP server** — a real FastMCP server (its own stdio process) exposing one tool,
   `vault_create_note(path, content)`: path-safety (confined to `VAULT_PATH`, extension
   whitelist), atomic write (temp + rename), fails if the note exists. **No vault git yet** —
   M0's only mutation is a non-destructive create and you watch every write in the REPL;
   git/undo lands with the first destructive op (append/patch/move/trash) or the first
   unattended write, whichever comes first (see `DECISIONS.md`).
4. **host** — minimal MCP host: spawn the obsidian server over stdio, discover/aggregate its
   tools, route tool calls to it. This is the extensibility seam every future capability *and*
   the auto-builder target (`VISION.md` §5.5, invariant 4).
5. **loop** — bare agent loop: given history + a user message, call the provider, run any tool
   calls through the host, feed results back, repeat until a final text answer. Tool errors
   return as error results so the model can recover.
6. **cli** — read a line from stdin, run one turn, print the reply. A REPL, not a daemon.

**Done when.** From a terminal, "make a note about X" creates `X.md` in the vault with sensible
content; the tool call round-trips through the MCP host to the obsidian server; the write is
atomic. `make check` (ruff + pyright + pytest) passes, with a unit test for `vault_create_note`
against a temp vault (create works, path traversal blocked, no overwrite).

**Resolved — real MCP server from the start** (was: in-process deferral). Building the actual
extensibility seam up front, per `VISION.md` invariant 4. Heavier M0 (adds the host + stdio
transport) but proves the real architecture end to end. See `DECISIONS.md` (2026-06-13).

---

## M1: complete the Obsidian server — DONE (2026-06-13)

**Status: done and verified.** All ten `vault_` tools work over MCP (smoke-tested end to end:
create/append/patch/move/trash each committed to vault git; move rewrote inbound links; trash
soft-deleted; unresolved links flagged; reads exclude trash). `make check` green — 20 tests.
Fully verifiable without the API key (vault ops are model-independent).

**Goal.** Flesh out the full `vault_` tool surface (`VISION.md` §5.6) on the MCP server stood up
in M0, and turn on vault git — the first destructive op is the trigger our decision named.
Design: `design/obsidian-server.md`.

**Scope:**

1. **Reads** — `vault_read_note`, `vault_list_notes(folder?)`, `vault_search_text(query, limit,
   regex)`, `vault_resolve_link(title)`, `vault_get_backlinks(path)`. Naive filesystem scans (no
   index yet — FTS5/graph are their own later milestones in §10).
2. **Mutations** — `vault_create_note` (+ optional frontmatter), `vault_append(under_heading?)`,
   `vault_patch_section(heading)`, `vault_move_note` (best-effort inbound `[[link]]` rewrite),
   `vault_trash_note` (soft delete to `/_trash`). Each is atomic and **git auto-committed**.
3. **Vault git** (`vault_git.py`) — init the vault repo on demand, commit per mutation, local
   identity, never pushed. Realizes invariant 1 now that destructive ops exist.
4. **Write-path validation** — reject malformed frontmatter before it lands; flag (don't reject)
   unresolved `[[links]]`. Table-column validation deferred (`BACKLOG.md`).

**Done when.** All ten `vault_` tools work over MCP; mutations land as vault git commits;
malformed frontmatter is rejected; `make check` passes with unit tests for each tool against a
temp vault.

---

## M2: keyword retrieval (FTS5) — DONE (2026-06-13)

**Status: done and verified.** FTS5 index live; `vault_search_text` BM25-ranked with snippets;
within-session upserts + trash-deletes confirmed via MCP smoke test; reindex-on-startup picks up
manual edits; regex fallback intact. `make check` green — 25 tests.

**Goal.** Replace the linear `vault_search_text` scan with a BM25-ranked SQLite FTS5 index, so
"what did I note about X" returns relevance-ranked real hits the model can read and cite
(`VISION.md` §10 keyword-retrieval). Design: `design/obsidian-server.md` § Index.

**Scope:**

1. **`index.py`** — FTS5 virtual table (`path UNINDEXED, content`, porter tokenizer) in
   `data/index.db`. Functions: `reindex(vault)`, `upsert(path, content)`, `delete(path)`,
   `search(query, limit)` → ranked `{path, snippet, score}`. One connection per call (low traffic).
2. **Wiring** — `config.index_path` (default `data/index.db`); host passes an absolute
   `INDEX_PATH` to the server. Server **reindexes on startup** (catches manual Obsidian edits) and
   **upserts/deletes incrementally** on every mutation (create/append/patch/move/trash).
3. **`vault_search_text`** — keyword path → FTS5 (ranked snippets); `regex=True` keeps the linear
   `vault.search_text` fallback (§5.6 "keyword/regex").

**Done when.** FTS5-ranked search returns relevant notes with snippets + scores; new/edited notes
are searchable within the session; the index rebuilds from the vault on start; `make check` passes
with unit tests for reindex/upsert/delete/search.

**Not in M2.** Automatic context assembly (§5.9) — retrieval stays tool-driven. Incremental
mtime/hash-keyed reindex + a file watcher come with the semantic-index milestone (`BACKLOG.md`).

---

## M3: scheduler — DONE (2026-06-13)

**Status: done and verified.** Multi-server host live; scheduler tools persist tasks to the vault
note + commit; due logic correct; on-open trigger runs due tasks; `_system/` excluded from search.
`make check` green.

**Goal.** Let the bot hold a persistent list of recurring tasks ("summarize my day", daily) and
run the due ones when it opens. Tasks live in data (a vault note), not core (invariant 5).
Design: `design/scheduler.md`.

**Scope:**

1. **Multi-server host** — generalize `MCPHost` to spawn N servers (obsidian + scheduler) and
   route tool calls to the owning server (`VISION.md` §5.5). Generic; no task content in core.
2. **Scheduler server** (`servers/scheduler/`) — store + tools. Task *definitions* (prompt,
   cadence ∈ on-open|daily|weekly, enabled) live in the vault note `_system/Scheduled.md`
   (visible/editable in Obsidian, versioned). Last-run timestamps live in
   `data/scheduler_state.json` (operational, gitignored). Tools: `schedule_task`,
   `list_scheduled_tasks` (with due status), `cancel_task`, `mark_task_ran`.
3. **On-open trigger** — at REPL start, the loop calls `list_scheduled_tasks`, runs each due task
   through `run_turn`, then `mark_task_ran`. Pure MCP (core doesn't import the server). "Daily"
   works via last-run timestamps even if you open the bot intermittently.
4. **`_system/` excluded** from vault listing/search/index (like `_trash`) so the scheduler note
   doesn't pollute knowledge results.

**Done when.** "Schedule a daily summary" persists a task in the vault note; reopening runs it
once per day; `make check` passes with unit tests for the store + due logic.

**Not in M3.** True unattended wall-clock firing (timer source in the daemon) — that's the
proactive-triggers milestone. On-open is the stand-in until the daemon exists.

---

## M4: semantic vault index — DONE (2026-06-13)

**Status: done and verified.** `vault_search` server: heading-aware chunking + local fastembed
(bge-small) embeddings + NumPy brute-force cosine + FTS5, hybrid-fused via RRF. `semantic_search`
recalls by meaning (a synonym query sharing no words ranked the right note first). Reindex on
startup. `make check` green — 37 tests. `sqlite-vec` unusable (this Python can't load extensions)
→ NumPy brute-force; sqlite-vec/LanceDB are the scale path.

## M5: memory server — DONE (2026-06-13)

**Status: done and verified.** `memory` server: one SQLite store (`data/memory.db`), profile +
recall tiers split by `kind`. Recall-tier entries embedded (shared `embedding` package, extracted
from `vault_search`); `memory_recall` is vector-only cosine over active recall entries; profile
returned wholesale under a char cap. Mechanical `memory_consolidate` (dedup by `keys`, evict oldest
profile over cap). 9 tools live over MCP (incl. `memory_list` for auditing) — round-trip
smoke-tested (remember → profile/recall/open tasks ranked by meaning; list shows stale history).
`make check` green — 48 tests. Design: `design/memory-server.md`.

Tool-driven for M5 (no auto profile injection — that's Context-assembly v2, §5.9); the store is the
**source of truth**, persistent (no reindex on start), gitignored (local-only, no remote backup).

## M6: context assembly v2 (§5.9) — DONE (2026-06-14)

**Status: done and verified.** `src/bot/context.py` `assemble_context` wired into `run_turn` (built
once per turn, reused across tool-use iterations). End-to-end against real servers: one message
("what should I focus on this summer?") auto-pulled profile + a meaning-matched memory fact + the
vault note, each provenance-tagged, into the system prompt — no tool call. Char budget profile-first
then remainder split; failing/empty sources skipped; all-empty → base SYSTEM unchanged. `make check`
green — 53 tests.

**Goal.** Make retrieval automatic instead of agentic: per turn, inject the profile + top-k memory +
top-k vault notes (provenance-tagged, one token cap) into the system prompt, so a fresh session has
continuity from memory and answers grounded in notes — without the user calling a tool. This is the
highest-leverage step toward the "feel like a real chatbot" north-star. Next in VISION §10's
dependency order (deps memory + semantic index, both built). Design: `design/context-assembly.md`.

**Scope — build in this order:**

1. **`src/bot/context.py`** — `assemble_context(host, user_message, base_system) -> str`. Calls
   `memory_get_profile`, `memory_recall(query, k)`, `semantic_search(query, k)` over MCP; formats
   with provenance (`memory#id`, `vault: path › heading`); allocates one char budget across sources;
   degrades gracefully (skip a failing/empty section; all-empty → base SYSTEM unchanged).
2. **Wire into the loop** — `run_turn` calls `assemble_context` once per turn (on the user message),
   reuses the assembled system across the turn's tool-use iterations. Search tools stay available.
3. **Tests** — `assemble_context` against a fake host: profile always present, sections formatted,
   budget truncates, empty stores → base, failing retrieval skipped.

**Done when.** Fresh REPL + a fact in memory + a note in the vault → a grounded, cited answer with no
tool call by the user. `make check` green with the unit tests above.

**Not in M6** (deferred → `BACKLOG.md`): graph one-hop (`expand_context`), real tokenizer budget,
static/dynamic prompt-cache split, transcript compaction + session-summary-on-close (those distill
the *conversation*; M6 assembles the *stores*).

## M7: conversation memory (rolling summary + compaction) — DONE (2026-06-14)

**Status: done and verified.** `src/bot/conversation.py`: `Conversation` (messages + rolling
summary) + `maybe_compact` folds old turns into the summary (LLM call) when real user turns exceed
`COMPACT_AFTER_TURNS=12`, keeping `KEEP_RECENT_TURNS=4` verbatim; cut lands only on a real user turn
(tool-pairing safe). `run_turn` takes a `Conversation`, compacts first, enriches the retrieval query
with the summary tail, and injects `# Conversation so far`. `cli` holds one `Conversation` (REPL +
scheduled tasks share it). `make check` green — 57 tests. Design: `design/conversation-memory.md`.

**Not in M7** (deferred → `BACKLOG.md`): session-summary persistence / resume-after-restart (needs a
real session lifecycle → daemon); distilling the summary into the memory store as an `episode`;
real-tokenizer thresholds.

## M8: daemon + event router + timer source — DONE (2026-06-14)

**Status: done and verified.** `src/bot/daemon.py` (`Daemon`: queue + `_router` + `Event`) +
`src/bot/sources.py` (`StdinSource`, `SocketSource`, `TimerSource`, `ShutdownSignal`) +
`src/bot/client.py` (`sipa-client`). `cli` builds the host + one `Conversation`, wires the three
sources, runs the daemon. on-open tasks fire only on the first (startup) tick; daily/weekly on any
due tick. Per-call token usage logged to `sipa.cost`. `make check` green — 62 tests (router reply +
error isolation, socket multi-turn round-trip, real `_make_handler` wiring over socket, timer
cadence). Design: `design/daemon.md`.

**Goal.** Turn the REPL into an always-on daemon: a long-lived process holding the host + a single
conversation, fed by an **event router** that dispatches inbound events (stdin + a local socket now;
Telegram/webhooks later) to turns, plus a **timer source** that fires due scheduled tasks on
wall-clock time (not just on-open). Realizes VISION §10 "Daemon + agent core" + "Proactive triggers".

## M9: local model option — DONE (2026-06-14)

`make_provider(settings)` picks by `provider` config ("anthropic" | "local"). `LocalProvider` is a
scaffold (raises `NotImplementedError`) — the seam is reserved, not wired to a runtime yet.

## M10: basic desktop app — DONE (2026-06-14)

Extremely basic Tauri v2 shell in `desktop/`: chat UI → `ask` command → daemon Unix socket. Compiles
(`cargo check`). Design: `design/desktop.md`. Telegram dropped per user. Production bundling (real
icons) + persistent connection deferred.

## M11: session-summary persistence — DONE (2026-06-15)

On shutdown `_persist_session` distills the session (`finalize_summary`) and **supersedes a single**
session-summary episode (keyed `session-summary`) — each summary already folds the prior, so old
ones are redundant; we keep exactly one active (no accumulation, no window to tune). On startup
`_resume_session` seeds `Conversation.summary` from it → resume warm. Skips empty sessions, ignores
model-made episodes, bad saves never block exit.

## M12: loop cap + cost rollup — DONE (2026-06-15)

Agent loop now warns at `WARN_ITERATIONS=15` (logs, keeps going — won't pause long tasks) and hard-
stops a runaway turn at `MAX_ITERATIONS=40` (returns a notice, ends alternating). `AnthropicProvider`
accumulates session token totals and logs per-call + running **dollar cost** (`cost_usd`, prices in
config; defaults = Opus 4.8 $5/$25). Decided: auto-builder coding will bill to the Max subscription
via Claude Code (`DECISIONS.md`).

## M13: web search — DONE (2026-06-15)

`web` MCP server: `web_search(query, max_results)` over a swappable `SearchBackend` protocol
(`TavilyBackend` today; SearXNG/Brave later — one-class change). Gives the bot current/external info
→ sourced research notes. Spawns only when `TAVILY_API_KEY` (in `.env`) is set. Live-verified against
Tavily. `web_fetch` (page extract) is the natural follow-up. Design: `design/web-search.md`.

## M14: base toolbox tier 1 — DONE (2026-06-15)

Toward "everything Claude can do" (each capability a server / loop feature). **Adaptive thinking**
on by default (`config.thinking`, provider). **`fs` server** — `read_file`/`list_dir`/`read_image`
confined to `FS_READ_ROOTS` (path-safe, read-only). **Vision** — `host._to_content` passes image
content from tool results to the model. Design: `design/local-files.md`. Live-verified.

## M15: sub-agents — DONE (2026-06-15)

Both modes. **Fan-out:** `delegate(tasks)` → `run_subagents` runs each as an isolated `run_turn`
(fresh Conversation, same host tools), concurrent up to `MAX_SUBAGENTS=5`. **Background:**
`delegate_background(task)` → `BackgroundDelegator.start` spawns a detached worker, returns an ack
immediately (keep chatting), prints the result on completion. Both offered only on top-level turns
(`allow_delegate`), so sub-agents can't recurse. Design: `design/sub-agents.md`.

**Refinements (BACKLOG):** route background completions through the event router per-source (desktop
app gets them; bot presents in context); shared cap across fan-out + background.

## M17: interactive code execution — DONE (2026-06-16)

Approval round-trip (`Ask` threaded source→router→`run_turn`; `_approved` gate) + `exec` server
(`run_shell`, scoped to `EXEC_ROOT`, off by default, timeout/cap). `run_shell` ∈ `APPROVAL_REQUIRED`:
interactive asks `[y/N]`, unattended (ask=None) denied. Design: `design/code-execution.md`.

**Permission UX (built):** `Approver` — `approval_mode` ask|trust + in-session "always" allowlist
(Claude-Code-style: free for safe, prompt for risky, allowlist/mode to cut prompts).

**Built since:** `vault_undo` (revert last change), per-action summaries (system prompt), and the
**desktop approval card** (Tauri `ask` handles `ASK_PREFIX` → Approve/Always/Deny card → `approve`
command; compile-verified, wants a live GUI run). **Remaining (BACKLOG):** the **sandbox**
(autonomous/unattended shell — the autobuilder).

**Base toolbox left:** filesystem write (reversible via git), computer use (tier 3). Connectors
(Gmail/Calendar/Drive) separately.

## Desktop dashboard — backbone DONE (2026-06-17)

Reworked the desktop from a fixed chat window into a **customizable module grid**: each capability
is a tile on a 12-col `react-grid-layout` grid; an "edit" toggle (status bar) enables drag-to-place
(snap-to-grid) + add/remove via a palette; the single layout persists to `localStorage`
(`sipa.dashboard.v2`) across sessions. Chat is the one live module (7×12); Token Usage, Background
Agents, Scheduler are **placeholder tiles** (built individually, not yet wired). Design:
`design/dashboard.md`. Build-verified (`tsc && vite build`) + GUI-verified (drag works).

Pinned **react-grid-layout v1.5** (the 2.x rewrite's legacy shim was buggy). The drag-dead bug was
react-draggable reading `process.env` in-browser → `ReferenceError` in `handleDragStart`; fixed with
a `window.process` shim in `index.html` + a Vite `define`. `React.StrictMode` left off (RGL +
`findDOMNode` flakiness). See `DECISIONS.md` (2026-06-17).

## Current task — wire the dashboard modules to live daemon state

Turn the placeholder tiles into real mini control-panels, fed by the M16 push channel (the desktop's
persistent `:subscribe` socket connection). Build modules one at a time.

**Telemetry backbone — DONE (2026-06-17).** One typed channel, not a separate transport (decided:
`DECISIONS.md`). Every pushed line is either chat (plain, → `sipa-push`) or telemetry
(`TELEMETRY_PREFIX` + JSON `{topic, …}`, → `sipa-telemetry`). `Daemon.emit_telemetry(topic, payload)`
broadcasts; the terminal REPL ignores telemetry lines; the desktop routes on prefix + `topic`
(`telemetry.tsx` holds latest-per-topic, modules read their slice via `useTelemetry`). `topic`-
filtered *subscriptions* reserved for a future second consumer.

**Token Usage — DONE (2026-06-17).** `ModelProvider.usage()` returns session + last-call tokens +
`cost_usd`; `cli` pushes a `cost` snapshot after every turn via `daemon.after_turn`. Desktop: the
`Token Usage` tile (`modules/Cost.tsx`) + the status-bar session cost now render live. Verified:
`make check` (111 tests) + `tsc`/`vite build` + `cargo check`.

**Next:** **Background Agents** (delegate/`delegate_background` status — needs the delegator to emit
start/finish telemetry) then **Scheduler** (due/next from `list_scheduled_tasks`). Same envelope.

## Later (not started)

A self-hosted SearXNG backend (full OSS), web-image vision, real-tokenizer context budget +
hard spend ceiling, graph expansion, incremental/mtime reindex,
memory's own local-only git, wiring `LocalProvider` to a real runtime, and — only if independent
per-session episodes are added later — relevance/decay-based pruning of those (`BACKLOG.md`).
