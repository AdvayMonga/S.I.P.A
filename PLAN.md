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

## Next (not started)

The **daemon + event router + true timer source** (always-on, real proactive triggers), then
**Context assembly v2** (§5.9 — always-inject profile + fuse memory/vault under one token budget).
Graph expansion (`expand_context`), incremental/mtime-keyed reindex, and memory's own local-only
git are deferred (`BACKLOG.md`).
