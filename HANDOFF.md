# HANDOFF.md

Save-state for resuming cold. Overwritten each session end. Read this first, then `PLAN.md`.

_Last updated: 2026-06-13._

## What this is

S.I.P.A. — a personal AI bot with an Obsidian vault as durable memory. Every capability is an MCP
server; the core (`src/bot`) only routes turns and spawns servers, never imports them. North-star:
`VISION.md`. The self-improving auto-builder (`siloop.md` etc.) is **not built** — built by hand
only after the bot works (bot → loop → autonomy).

## Status: M0–M8 done, all on GitHub

- **M0** — loop: terminal → Claude → MCP host → vault. Live-verified.
- **M1** — Obsidian server: 10 `vault_` tools + atomic writes + frontmatter validation + vault git.
- **M2** — keyword retrieval: SQLite FTS5, BM25-ranked `vault_search_text`.
- **M3** — scheduler: recurring tasks (definitions in vault note `_system/Scheduled.md`, last-run in
  `data/`), run on open. Host generalized to spawn N servers.
- **M4** — semantic index: `vault_search` server — chunk + local fastembed (bge-small) + NumPy
  cosine + FTS5, hybrid-fused (RRF). `semantic_search` recalls by meaning.
- **M5** — memory server: one SQLite store (`data/memory.db`), profile + recall tiers split by
  `kind`. Recall-tier embedded (shared `embedding` package); `memory_recall` = vector-only cosine;
  profile returned wholesale under a char cap; `memory_consolidate` dedups by `keys` + evicts. 9
  `memory_` tools (incl. `memory_list` for auditing — the read tool a future Tauri inspector
  renders), tool-driven. **Source of truth** (persistent, not reindexed), gitignored.
- **M6** — context assembly v2 (§5.9): retrieval flipped agentic → **pushed**. `src/bot/context.py`
  `assemble_context` runs once per turn, injecting profile + top-k memory + top-k vault notes
  (provenance-tagged, one char budget) into the system prompt. A fresh session now *knows* you with
  no tool call. Search tools still available for deep dives.
- **M7** — conversation memory: `Conversation` (messages + rolling summary). `maybe_compact` folds
  old turns into the summary when the window grows (keeps recent verbatim, tool-pairing safe); the
  summary enriches retrieval + is injected as `# Conversation so far`. The within-session HANDOFF.
- **M8** — daemon: REPL → always-on process. One serialized event router (queue + `Conversation`)
  fed by sources — `StdinSource` (REPL), `SocketSource` (Unix socket, external clients via
  `sipa-client`), `TimerSource` (wall-clock fires due scheduled tasks; on-open once at startup).
  Per-call token usage logged to `sipa.cost`.
- **Refactor** — `servers/` at repo root; shared infra extracted to `vaultfs` + `embedding`.

`make check` green: ruff + pyright + **62 tests**.

## Layout

```
src/bot/       core: config, cli (builds host + sources, runs daemon), daemon (router + queue),
               sources (stdin/socket/timer), client (sipa-client), host (multi-server), loop,
               context (per-turn pushed retrieval), conversation (rolling summary + compaction),
               provider (+ token/cost log)
src/vaultfs/   SHARED infra: vault.py (path-safe fs ops), vault_git.py (local git).
src/embedding/ SHARED infra: Embedder protocol + FastEmbedEmbedder (bge-small). vault_search +
               memory depend downward on it. bot (router) never imports shared infra; no server
               imports another.
servers/       capabilities (independent MCP processes, spawned by the host):
  obsidian/      10 vault_ tools, FTS5 keyword index (obsidian-only)
  scheduler/     recurring-task store (vault note) + tools
  vault_search/  chunk, index (hybrid RRF), server
  memory/        store (profile+recall tiers, one SQLite table) + 9 memory_ tools
tests/
data/          index.db, vault_search.db, scheduler_state.json (rebuildable) + memory.db
               (SOURCE OF TRUTH, not rebuildable). All gitignored.
```

Four servers run per session: obsidian, scheduler, vault_search, memory → 25 aggregated tools.

## How to run / verify

- **Run:** `make run` (= `uv run sipa`) starts the **daemon**: it binds a Unix socket
  (`data/sipa.sock`), starts the wall-clock timer (fires due scheduled tasks; on-open at startup),
  and gives you the terminal REPL. `Ctrl-D` exits. First run downloads the ~50MB embedding model.
- **External client:** `uv run sipa-client` connects to a running daemon's socket from another
  terminal (the path desktop/Telegram front-ends will reuse).
- **Check:** `make check` (ruff + pyright + pytest). Python pinned 3.12 via `uv`.
- **Config:** `.env` (gitignored) holds `ANTHROPIC_API_KEY` + `VAULT_PATH` (both filled).
  Default model `claude-opus-4-8`, thinking off.

## Live environment (real, not test)

- **Vault = `~/Desktop/CORE`** (the user's real vault, ~7 notes). Git-versioned locally: a
  `baseline` commit (Advay Monga) + per-mutation `S.I.P.A.` commits. **Local-only, never pushed.**
  Undo all bot history: `rm -rf ~/Desktop/CORE/.git`.
- **Code repo** has remote `origin` (`AdvayMonga/S.I.P.A`). **Push after each commit** (working
  agreement, also in `.claude/settings.local.json` permission allowlist, gitignored).

## Context not obvious from code

- **Retrieval is pushed, not just agentic (as of M6)** — every turn, `assemble_context` injects the
  profile + top-k memory + top-k vault into the system prompt automatically (the model no longer
  needs to call a tool to recall). Writing memory is still tool-driven (`memory_remember`), and the
  search tools remain for deep dives. **Conversation now lives for the daemon's lifetime** (M8) —
  continuity while running, across stdin + socket + timer events (one shared `Conversation`). It does
  NOT survive a daemon restart yet; durable continuity comes from the memory store + vault. Within a
  run, M7's rolling summary + compaction bound the window; persisting the summary across restarts
  (distill to an `episode`) is deferred (`BACKLOG.md`).
- **Retrieval is tool-driven** — model calls `vault_search_text` (keyword) / `semantic_search`
  (meaning) → reads → cites. Automatic context assembly (§5.9) is later.
- **Scheduling now fires on wall-clock (M8)** — `TimerSource` checks due tasks every
  `timer_interval` (60s default) while the daemon runs; on-open fires once at startup. Last-run
  timestamps still make "daily/weekly" correct across intermittent runs.
- **Cross-server coupling debt — RESOLVED (2026-06-13)** — vault fs/git extracted to the top-level
  `vaultfs` package; servers depend downward on it, none import each other. See `DECISIONS.md`.
- Why-decisions: `DECISIONS.md`; deferred scope: `BACKLOG.md`; per-feature designs: `design/`.

## Next (see `PLAN.md`)

Needs user input before building:
1. **Desktop app** (Tauri) — toolchain (Rust+Node) + product decisions. The socket (`sipa-client`)
   is the seam it plugs into.
2. **Telegram source** — needs a bot token from the user. Then it's just another `Source`.
3. **Local model option** — which model/runtime.

Buildable without input: token budgeting/cost rollups, session-summary persistence across restarts
(distill to a memory `episode` on shutdown), graph one-hop, incremental reindex — all in `BACKLOG.md`.

## Gotchas

- Servers run as subprocesses (`python -m servers.<name>.server`), reading paths from env, never
  importing core. `vault_search` re-embeds the whole vault on start (fine for a small vault).
- `_system/` and `_trash/` are excluded from vault listing/search/index.
- If an allowlisted command still prompts, restart Claude Code to reload settings.
