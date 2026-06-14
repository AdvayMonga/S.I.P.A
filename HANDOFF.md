# HANDOFF.md

Save-state for resuming cold. Overwritten each session end. Read this first, then `PLAN.md`.

_Last updated: 2026-06-13._

## What this is

S.I.P.A. — a personal AI bot with an Obsidian vault as durable memory. Always-on-daemon design
where every capability is an MCP server. North-star spec: `VISION.md`. The self-improving
auto-builder (later) is specced in `siloop.md` / `sandbox.md` / `VERIFIER.md` / `REVIEW.md` —
**not built yet; built by hand only after the bot works** (bot → loop → autonomy).

## Status: M0–M2 done, all on GitHub

- **M0** — daemon-less loop: terminal → Claude → MCP host → vault. Live-verified against the real
  vault.
- **M1** — full Obsidian MCP server: 10 `vault_` tools (read/list/search/resolve/backlinks +
  create/append/patch/move/trash), atomic writes, frontmatter validation, **vault git**
  (auto-commit per mutation, local-only).
- **M2** — keyword retrieval: SQLite **FTS5** index (`data/index.db`), BM25-ranked
  `vault_search_text`; reindex on startup + incremental upsert/delete on mutations.
- **Refactor** — `servers/` moved to the repo root (out of `src/bot/`) to match `VISION.md` §4.

`make check` green: ruff + pyright + **25 tests**.

## Layout

```
src/bot/      core: config, cli, host, loop, provider   (the brain; never imports a server)
servers/      capabilities: independent MCP processes    (the limbs)
  obsidian/     vault.py, vault_git.py, index.py, server.py
tests/
data/         index.db (gitignored, rebuildable)
```

## How to run / verify

- **Run:** `make run` (= `uv run sipa`) — REPL against the real vault. `Ctrl-D` exits.
- **Check:** `make check` (ruff + pyright + pytest). Python pinned 3.12 via `uv`.
- **Config:** `.env` holds `ANTHROPIC_API_KEY` + `VAULT_PATH` (gitignored; both filled in).
  Default model `claude-opus-4-8`, thinking off, `MODEL=…` overridable.

## Live environment (real, not test)

- **Vault = `/Users/advaymonga/Desktop/CORE`** — the user's real Obsidian vault, ~7 personal
  notes. Now git-versioned locally: a `baseline` commit (authored "Advay Monga") + the bot's
  per-mutation commits (authored "S.I.P.A."). **Local-only, never pushed.** Undo all bot history
  with `rm -rf ~/Desktop/CORE/.git`.
- **Code repo** has remote `origin` (`AdvayMonga/S.I.P.A`). **Push after each commit** (working
  agreement). Interactive flow commits to `main` directly.
- Permissions allowlist in `.claude/settings.local.json` (gitignored) so git/make/uv/pytest/
  ruff/pyright/python-m don't prompt.

## Context not obvious from code

- **No cross-session memory yet** — conversation history is per-REPL-run; closing resets it. The
  memory server (the bot's model of you) is a later milestone.
- **Retrieval is tool-driven** — the model calls `vault_search_text` → `read` → cites. Automatic
  context assembly (`VISION.md` §5.9) is later.
- Why-decisions live in `DECISIONS.md`; deferred scope in `BACKLOG.md`; per-feature designs in
  `design/` indexed by `DESIGN.md`.

## Next (pick one — see `PLAN.md` "Next")

1. **Semantic index** — chunking + embeddings + `sqlite-vec`, hybrid-fused (RRF) with the FTS5
   index. Recall by meaning. The big retrieval upgrade.
2. **Memory server** — separate profile + episodic recall store, reusing the index machinery.

## Gotchas

- The Obsidian server runs as a subprocess (`python -m servers.obsidian.server`) spawned by the
  host; it reads `VAULT_PATH` + `INDEX_PATH` from env, never imports core.
- `vault_move_note` link rewrite is stem-based; table-column validation not yet done (`BACKLOG`).
- If a permission prompt reappears for an allowlisted command, restart Claude Code to reload
  `.claude/settings.local.json`.
