# design/memory-server.md

The memory server — the bot's **model of you**, kept separate from the vault. Realizes
`VISION.md` §5.8. The vault is *authored knowledge*; agent memory is *distilled facts about you
+ operational state*, machine-managed (written, consolidated, pruned), never raw transcripts.

## Two tiers, one store

- **Profile tier** — small, capped, the always-available core: standing preferences, instructions,
  key entities, and a house-style note. Returned wholesale by `memory_get_profile`.
- **Recall tier** — episodic summaries + facts, retrieved top-k by meaning. The long tail.

One SQLite table (`data/memory.db`), a `tier` column splits the two. Each entry also has a `kind`
(`VISION.md` §5.8). `kind` → `tier` mapping (so `memory_remember` needs no extra param, matching
the spec's signature):

| tier | kinds |
|---|---|
| profile | `preference`, `instruction`, `entity`, `house_style` |
| recall | `fact`, `episode`, `task` |

## Reused machinery — `Embedder` extracted to shared infra

Recall = embed the query, cosine over stored entry vectors — the **same** embedding the
`vault_search` server uses. That embedder lived in `servers/vault_search/embed.py`; importing it
from the memory server would recreate the cross-server coupling we just removed (see
`DECISIONS.md`). So `Embedder` + `FastEmbedEmbedder` move to a **top-level `embedding` package**
(`src/embedding/`), parallel to `vaultfs`. Both servers now depend downward on it; neither imports
the other. The ~5-line cosine is small enough to live in each store; a shared vector-store
abstraction over two different schemas would be premature (only two consumers, different shapes).

Recall is **vector-only** for M5 (entries are short distilled facts). Hybrid vector+FTS RRF (as in
`vault_search`) is a possible later enhancement — `BACKLOG.md`.

## Tools (`servers/memory/server.py`)

| Tool | Tier | Purpose |
|---|---|---|
| `memory_get_profile()` | profile | concat active profile entries; enforce a char cap |
| `memory_recall(query, k, kind?)` | recall | embed query → cosine → top-k `{id, kind, content, score}` |
| `memory_list_open_tasks()` | recall | active `kind='task'`, not done — working memory across sessions |
| `memory_remember(content, kind, keys?)` | both | distill a durable entry; tier inferred from kind |
| `memory_update(id, content)` | both | **supersede**: write a new entry, mark the old stale (keeps history) |
| `memory_forget(id)` | both | soft delete (excluded from all reads) |
| `memory_complete_task(id)` | recall | mark an open task `done` (keeps it as history) — the only path to the `done` status the schema mandates |
| `memory_consolidate()` | both | first-class job — see below |

**Only recall-tier entries are embedded.** Profile is returned wholesale, never vector-searched,
so profile entries store `vec = NULL` — no wasted embed calls. `memory_recall` cosines over active
recall entries only. The cap (`PROFILE_CAP = 2000` chars) is a constant in `store.py`:
`get_profile` truncates to it as a safety bound; `consolidate` is what actually evicts.

## Store (`servers/memory/store.py`)

Schema: `memory(id, tier, kind, content, keys, status, vec, created_at, superseded_by)`.
`status` ∈ `active` / `done` (tasks) / `stale` (superseded) / `deleted`. `keys` = optional
space-separated tags for conflict detection. `created_at` is injected (a `now` param) for
deterministic tests, mirroring the scheduler's `is_due`.

**Consolidation is mechanical** (no LLM — `VISION.md` §5.8's rules are all deterministic):
- **dedup / conflict** — active entries sharing non-empty `keys` → newest wins, older marked
  `stale`.
- **profile cap** — if active profile content exceeds the cap, supersede oldest profile entries
  until under cap (crude eviction; LLM summarization is the later refinement).
- returns `{superseded, profile_evicted}` (count of dedup-staled entries + count of profile
  evictions).

## Privacy & durability — a real consequence, flagged

`data/memory.db` is the **source of truth**, not a rebuildable index. This differs from
`index.db` / `vault_search.db`, which are derived and reindex from the vault on start. Two
consequences:
- **Privacy (correct):** it lives in gitignored `data/`, so it stays on the machine and is never
  pushed to the code remote (`VISION.md` §11). The bot's model of you doesn't leave the device.
- **Durability (the catch):** because `data/` is gitignored, memory has **no remote backup** — its
  only safety net is local (Time Machine), per `VISION.md` §6's local-backup guidance. Giving
  memory its own local-only git (like the vault's) is the durability upgrade — deferred to
  `BACKLOG.md`. Accepted for M5: source-of-truth in a gitignored dir, local backup only.

## Scope boundary — what M5 is NOT

- **No automatic per-turn profile injection.** Memory is **tool-driven** for now (the model calls
  `memory_get_profile` / `memory_recall`, exactly as it calls `vault_search`). Always-injecting the
  profile + fusing profile/memory/vault under one token budget is **Context assembly v2**
  (`VISION.md` §5.9), the next milestone — it touches the loop's system prompt; memory does not.
- **No automatic session-end distillation.** Distillation happens via the model calling
  `memory_remember` ("remember this"), or a scheduled "distill" task (reuse the M3 scheduler). A
  true on-close lifecycle hook belongs with the daemon (REPL session boundaries are fuzzy).

This keeps M5 = the store + tools + mechanical consolidation, which already satisfies `VISION.md`
§10's done-criteria: *recalls across sessions; profile stays under cap; consolidation merges and
supersedes.*
