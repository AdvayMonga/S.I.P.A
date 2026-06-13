# PLAN.md

The work queue. Near-term scope only; empties as work finishes. North-star specs are
`VISION.md` (the bot) and `siloop.md` (the loop) — this file holds what's *next*, not the whole
destination.

---

## Current milestone — M0: thin vertical slice

**Status (2026-06-13): code-complete, verified except the live model turn.** All five components
built and committed; `make check` green (ruff + pyright + pytest, 4 tests). MCP round-trip
smoke-tested end to end (host spawns the obsidian server, discovers `vault_create_note`, routes a
call, writes the note atomically, surfaces the overwrite error). **Remaining:** fill `.env`
(`ANTHROPIC_API_KEY`, `VAULT_PATH`) and run one live turn (`make run`) to confirm steps 5–6.

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

## Next (not started)

Per `VISION.md` §10: keyword retrieval (FTS5-backed `vault_search_text`), then the semantic
index (chunking, embeddings, graph). The daemon / host / event-loop infrastructure comes when
there's a brain worth keeping always-on — not before.
