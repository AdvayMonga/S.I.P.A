# design/obsidian-server.md

The Obsidian MCP server — act on the vault **by path** (`VISION.md` §5.6). Recall-by-meaning is a
separate server (vault-search, §5.7). As-built; supersedes the relevant parts of `siloop`/`sandbox`
only in the sense that this is the living design — the spec stays in `VISION.md`.

## Modules

- `vault.py` — pure filesystem ops: path safety, reads, atomic validated writes. No git, no MCP.
- `vault_git.py` — local-only git: init-on-demand, auto-commit per mutation. No network.
- `server.py` — the FastMCP server: registers the ten tools, commits after each mutation, and
  surfaces unresolved-link warnings. The only mutation entry point, so it owns the commit step.

## Tools

| Tool | Kind | Notes |
|---|---|---|
| `vault_read_note(path)` | read | raw content; errors if missing |
| `vault_list_notes(folder?)` | read | `*.md` under folder (or whole vault), `_trash` excluded |
| `vault_search_text(query, limit, regex)` | read | naive case-insensitive scan → path/line hits |
| `vault_resolve_link(title)` | read | filename-stem match → relative path or null |
| `vault_get_backlinks(path)` | read | scan for `[[stem]]` referencing the note |
| `vault_create_note(path, content, frontmatter?)` | write | fails if exists |
| `vault_append(path, content, under_heading?)` | write | non-destructive; insert at end of a section or EOF |
| `vault_patch_section(path, heading, content)` | write | replace a heading's body; heading must exist |
| `vault_move_note(old, new)` | write | rename + best-effort inbound `[[link]]` rewrite |
| `vault_trash_note(path)` | write | soft delete to `/_trash`, collision-numbered |

## Cross-cutting

- **Path safety** — relative only, `.md` allowlist, resolved path confined to the vault root.
- **Atomic writes** — temp file + `os.replace`; temp cleaned on failure.
- **Vault git** — every mutation is a commit (local identity `S.I.P.A. <sipa@localhost>`, never
  pushed). The repo is `git init`'d on first mutation. `commit` returns `None` when nothing
  changed (idempotent no-ops don't error).
- **Validation** — frontmatter must parse (`python-frontmatter`) or the write is rejected.
  Unresolved `[[links]]` are flagged in the tool's reply, not rejected (forward links are valid).

## Deliberately deferred (see `BACKLOG.md`)

- **FTS5 / graph index** — `search_text`, `resolve_link`, `backlinks` are unindexed scans now;
  fine for a personal vault, replaced by the keyword/semantic-index milestones (§10).
- **Table-column validation** — frontmatter is validated; consistent table columns are not yet.
- **`move_note` link rewrite is stem-based** — rewrites `[[old-stem]]`, not path-qualified links.
