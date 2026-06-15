# HANDOFF.md

Save-state for resuming cold. Overwritten each session end. Read this first, then `PLAN.md`.

_Last updated: 2026-06-13._

## What this is

S.I.P.A. — a personal AI bot with an Obsidian vault as durable memory. Every capability is an MCP
server; the core (`src/bot`) only routes turns and spawns servers, never imports them. North-star:
`VISION.md`. The self-improving auto-builder (`siloop.md` etc.) is **not built** — built by hand
only after the bot works (bot → loop → autonomy).

## Status: M0–M5 done, all on GitHub

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
- **Refactor** — `servers/` at repo root; shared infra extracted to `vaultfs` + `embedding`.

`make check` green: ruff + pyright + **47 tests**.

## Layout

```
src/bot/       core: config, cli (+ on-open scheduler trigger), host (multi-server), loop, provider
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

- **Run:** `make run` (= `uv run sipa`). On open it runs any due scheduled tasks, then a REPL.
  `Ctrl-D` exits. First run downloads the ~50MB embedding model (one-time).
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

- **Memory is tool-driven, not auto-injected** — the model calls `memory_get_profile`/
  `memory_recall`/`memory_remember` like it calls `vault_search`. Conversation history is still
  per-REPL-run; always-injecting the profile + fusing memory/vault under one token budget is
  Context-assembly v2 (§5.9). Memory is a durable *store* now, but nothing assembles it per-turn yet.
- **Retrieval is tool-driven** — model calls `vault_search_text` (keyword) / `semantic_search`
  (meaning) → reads → cites. Automatic context assembly (§5.9) is later.
- **Scheduling is on-open only** — true unattended wall-clock firing needs the daemon's timer
  source (a later milestone). "Daily" works via last-run timestamps even with intermittent use.
- **Cross-server coupling debt — RESOLVED (2026-06-13)** — vault fs/git extracted to the top-level
  `vaultfs` package; servers depend downward on it, none import each other. See `DECISIONS.md`.
- Why-decisions: `DECISIONS.md`; deferred scope: `BACKLOG.md`; per-feature designs: `design/`.

## Next (see `PLAN.md` "Next")

1. **Daemon + event router + timer source** — always-on, real proactive triggers + Telegram.
2. **Context assembly v2** (§5.9) — always-inject profile + fuse memory/vault under one token budget.

## Gotchas

- Servers run as subprocesses (`python -m servers.<name>.server`), reading paths from env, never
  importing core. `vault_search` re-embeds the whole vault on start (fine for a small vault).
- `_system/` and `_trash/` are excluded from vault listing/search/index.
- If an allowlisted command still prompts, restart Claude Code to reload settings.
