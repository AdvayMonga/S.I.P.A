# BACKLOG.md

Append-only list of deferred scope and review minors. Each entry: what, why deferred, where it
belongs.

---

## From M1 (Obsidian server)

- ~~**FTS5-backed `vault_search_text`**~~ — done in M2 (BM25-ranked FTS5).
- **Incremental mtime/hash-keyed reindex + file watcher** — M2 reindexes the whole vault on each
  server start (fine for a small vault) and upserts on bot mutations. Replace the full rebuild with
  a `watchdog`-driven, file-hash/mtime-keyed incremental reindex in the semantic-index milestone
  (`VISION.md` §5.7). This also picks up manual Obsidian edits live instead of at next start.
- **Graph-backed `resolve_link` / `get_backlinks`** — currently unindexed scans. Back with the
  link-graph edges table in the semantic-index milestone (§10).
- **Table-column validation** — write-path validation rejects malformed frontmatter but does not
  yet check markdown table column consistency (`VISION.md` §5.6). Add to `vault.validate_markdown`.
- **`vault_move_note` path-qualified link rewrite** — inbound link update is stem-based
  (`[[old-stem]]` → `[[new-stem]]`); it does not handle path-qualified or aliased links robustly.

## From the servers/ relocation

- **Per-server dependency isolation** — all servers currently share the core's single venv/
  `pyproject`. For true MCP independence (and future non-Python servers), give each server its own
  deps (its own `pyproject`/venv) and have the host spawn it with that environment. Top-level
  `servers/` is the structural signal; this is the enforcement.

## From M3 (scheduler)

- **Extract `vault_git` to shared server infra** — the scheduler imports `servers.obsidian.vault_git`
  to commit its `_system/Scheduled.md` changes. It's vault infrastructure, not obsidian logic; move
  it to a shared module (e.g. `servers/_shared/`) so cross-server git use isn't an obsidian dependency.
- **True timer firing** — M3 runs due tasks on-open. Unattended wall-clock scheduling needs the
  daemon's timer source + event router (proactive-triggers milestone, `VISION.md` §5.2/§5.10).

## From M4 (semantic index)

- **`sqlite-vec` / LanceDB at scale** — current vector search is brute-force NumPy because the uv
  Python's `sqlite3` can't load extensions. At larger scale, use a SQLite build with extension
  loading (for `sqlite-vec`) or LanceDB.
- **Incremental / mtime-keyed embed reindex** — `vault_search` re-embeds the whole vault on every
  start. Cache by file hash/mtime so only changed notes re-embed (pairs with the FTS mtime item).
- **Cross-server index freshness** — a note created mid-session isn't in the semantic index until
  next start. Solve with the daemon + a shared/event-driven index, not per-server reindex.
- **`expand_context` (graph)** — link-graph expansion of results (`VISION.md` §5.7) not yet built.
- **Shared vault-read infra** — DONE (2026-06-13): `vault.py` + `vault_git.py` extracted to the
  top-level `vaultfs` package (`src/vaultfs/`); all servers now depend downward on it, none import
  each other. See `DECISIONS.md`.
