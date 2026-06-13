# BACKLOG.md

Append-only list of deferred scope and review minors. Each entry: what, why deferred, where it
belongs.

---

## From M1 (Obsidian server)

- **FTS5-backed `vault_search_text`** — current search is a naive filesystem scan. Replace with
  SQLite FTS5 in the keyword-retrieval milestone (`VISION.md` §10). Fine for a personal vault now.
- **Graph-backed `resolve_link` / `get_backlinks`** — currently unindexed scans. Back with the
  link-graph edges table in the semantic-index milestone (§10).
- **Table-column validation** — write-path validation rejects malformed frontmatter but does not
  yet check markdown table column consistency (`VISION.md` §5.6). Add to `vault.validate_markdown`.
- **`vault_move_note` path-qualified link rewrite** — inbound link update is stem-based
  (`[[old-stem]]` → `[[new-stem]]`); it does not handle path-qualified or aliased links robustly.
