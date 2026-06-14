# design/semantic-index.md

The `vault_search` server — recall the vault **by meaning** (`VISION.md` §5.7). Separate from the
obsidian server (which acts by path). As-built.

## Pipeline

```
note ──chunk──> chunks ──embed──> vectors ──┐
                  └──────────────FTS5────────┤
query ──embed──> qvec ──cosine top-N─────────┼──RRF fuse──> ranked chunks
query ──terms──> FTS5 bm25 top-N ────────────┘
```

- **Chunking** (`chunk.py`) — heading-aware: frontmatter stripped, then split into one chunk per
  heading section (`path`, `heading`, `text`).
- **Embeddings** (`embed.py`) — `Embedder` protocol; default `FastEmbedEmbedder` (local
  bge-small, 384-dim, model loads lazily on first embed, never leaves the machine). Tests inject a
  deterministic stub so they stay offline.
- **Store + search** (`index.py`) — SQLite at `data/vault_search.db`: a `chunks` table (vectors as
  float32 blobs) + a `chunks_fts` FTS5 table. **Vector search is brute-force NumPy cosine** — this
  Python's `sqlite3` can't load extensions, so no `sqlite-vec`; fine at personal-vault scale.
  **Hybrid** = Reciprocal Rank Fusion of the vector ranking and the FTS5 keyword ranking
  (`score = Σ 1/(60 + rank)`), so a chunk strong in either channel surfaces.

## Tools

| Tool | Purpose |
|---|---|
| `semantic_search(query, k)` | hybrid recall → JSON `path/heading/snippet/score` |
| `index_status()` | chunk + note counts |

## Lifecycle

Reindex (embed the whole vault) on server start — picks up manual Obsidian edits. Within a session,
a note created via obsidian isn't in the semantic index until next start (it's still found by
obsidian's incrementally-updated keyword search). Cross-server freshness is a daemon-era concern.

## Deferred (`BACKLOG.md`)

- `sqlite-vec` / LanceDB at scale (needs a SQLite build with loadable extensions, or a different
  vector backend); incremental mtime/hash-keyed reindex; cross-server index freshness;
  `expand_context` (link-graph expansion); shared vault-read infra (currently imports
  `servers.obsidian.vault`).
