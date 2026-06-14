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
