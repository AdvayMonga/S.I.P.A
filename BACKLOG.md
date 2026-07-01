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

## For the Context-assembly v2 milestone (`VISION.md` §5.9) — production-quality concerns

The three-source fused-under-budget design is the industry-standard RAG+memory shape; it's correct.
These are the upgrades real systems add *around* it. Most don't matter until assembly is live and
the bot actually knows you across sessions — revisit when building this milestone, not before.

- **Retrieval quality (highest leverage).** Plain top-k similarity is mediocre. In priority order:
  (a) **rerank** the top ~N candidates with a cross-encoder — reads query+chunk together, usually the
  single biggest quality jump (VISION §12 already flags "add if precision is weak" — this is where);
  (b) **query transformation** — ~~rewrite the user's literal words before searching: resolve pronouns
  from history~~ DONE 2026-06-18 (`query.py`, gated LLM rewrite; see DECISIONS). Still open under (b):
  split into sub-queries, optionally HyDE (embed a hypothetical answer); (c) **chunking** tuning —
  overlapping windows, small-to-big (embed small, return the parent section).
- **When to retrieve at all.** Today the model decides via tool calls (agentic retrieval — already
  good). For pushed assembly, add light routing so trivial turns ("thanks!") don't pull noise into
  the budget.
- **Memory lifecycle (the genuinely hard part, scale-independent).** Consolidation/prune is already
  scoped (§5.8) but the sharp edges: *what's worth distilling* (junk vs. durable fact); *contradiction*
  ("vegetarian" last month vs. "had steak" today — newest-wins is a heuristic, not a solution);
  *decay* (relevance = recency × importance × frequency, not just similarity); *dedup/merge* of
  near-duplicate memories. These determine whether memory helps or rots.
- **Budget packing & ordering.** Under a token cap, selecting the best subset is a small knapsack
  problem; also place the strongest chunks at the start/end of context ("lost in the middle"), and
  dedup the same fact appearing in both memory and the vault so it isn't paid for twice.
- **Provenance & injection.** Pulling untrusted vault/note text into context is an attack surface
  ("ignore previous instructions" in a note). Keep provenance tags (already in §5.9) and treat
  retrieved content as data, not instructions.
- **Eval.** Don't eyeball assembly quality — extend the retrieval golden set to measure
  recall@k / faithfulness / answer-relevance so changes here are gated, not guessed.

Deferred deliberately: latency budgets, ANN/HNSW, multi-tenant permission-filtered search — these
are operational-scale taxes that don't bite a single-user local bot. Revisit only if something hurts.

## 2026-06-14 — Rolling conversation summary (M6 follow-up)

Approved during M6 planning as "a good idea for later." Maintain a short rolling summary of the
conversation and use it to enrich the retrieval query in `assemble_context` (so follow-ups like
"and the next step?" retrieve against conversation state, not just the bare message). Pairs with the
deferred transcript-compaction work (the within-session "HANDOFF") and overlaps the existing
"query transformation" bullet above — implement them together. M6 ships with the raw user message as
the query; this is the first refinement once it's in use.

## 2026-06-14 — Daemon follow-ups (M8 deferrals)

- **Token budgeting + cost rollups.** M8 logs per-call `tokens in/out` (`sipa.cost`). A real
  per-turn/session cost rollup with pricing, and an actual token *budget* on context assembly (pairs
  with the real tokenizer, M6 deferral), are still open. VISION lists budgeting with the daemon.
- **Session-summary persistence across restarts.** Now that the daemon gives a real session
  lifecycle, persist M7's rolling summary on shutdown (and optionally distill it into the memory
  store as an `episode`) so a restart resumes warm. M8 keeps the summary in-process only.
- **Telegram + webhook sources.** Just more `Source`s feeding the same router. Telegram needs a bot
  token from the user; webhooks need an ingress. Deferred to the event-sources milestone.

## From M18 (concurrent chats)

- **Tighter Stop for in-flight `run_shell`** — stopping a thread mid-shell-command cancels the turn
  immediately (`[stopped]`), but the orphaned subprocess in the `exec` server keeps running until its
  own timeout cap, then dies. Acceptable for now (Stop is prompt for the user; the subprocess is
  bounded). A tighter kill needs the `exec` server to handle MCP request-cancellation and terminate
  its subprocess — cross-process, deferred. Belongs in `design/code-execution.md`.
- **Fold scheduled tasks + `delegate_background` into the thread pool** — the grand unification: a
  scheduled fire / delegated task becomes an auto-created thread that runs and goes `ready`. M18
  keeps them on their current paths (broadcast / detached worker). See `design/concurrent-chats.md`.

## From M19.x (desktop live state)

- ~~**Unified `:snapshot` command**~~ — done when the scheduler tile landed: `:snapshot` replaces
  `:threads`/`list_threads`, returning `{threads, scheduled}` in one fetch. Threads + Scheduler both
  seed from it on mount, then apply push deltas. (Each still fetches the verb separately; folding to
  a single shared on-mount fetch is a later micro-opt.)

## From scheduler tile

- **Interactive scheduler tile** — the tile is display-only today (read the task list). Add
  cancel / enable-toggle / add-task actions; needs new socket control verbs + store mutators
  (`scheduler` server already has `cancel_task`; `enabled` toggle + UI add are new). The model can
  already do all of this via chat, so this is convenience, not capability.

## From research flow (v1 is a playbook over existing tools — see design/research.md)

- ~~**Adversarial claim-verification (deep research)**~~ — DONE 2026-06-18 (`verify_claims` tool +
  `src/bot/verify.py`): independent skeptic sub-agents refute each key claim before the note lands;
  skeptical aggregation (refuted if any, supported only if unanimous). See DECISIONS + design/research.md.
- **Code-side citation validation** — the better grounding mechanism than prompt-trust: after the note
  is drafted, validate every footnote URL was actually `web_fetch`ed this turn. Needs to see both the
  fetch history and the note → belongs in the **core** agent loop, not a leaf tool. Build when a
  hallucinated cite first appears.
- **Schema-enforcing `vault_write_research_note` tool** — v1 trusts the playbook for the note schema.
  If formatting drifts in practice, add an obsidian-server tool that enforces frontmatter/header/
  footer/sources/dedup-append in code.
- **Multi-agent fan-out per entity** — for large multi-entity research, spawn a sub-agent per entity
  in parallel (reuses the existing `delegate` fan-out), then synthesize into one note or split notes.

## From tool-loop token work (2026-06-30 — see DECISIONS)

- **Split static system from volatile retrieval for across-turn caching** — today `assemble_context`
  bakes retrieval into `system`, so the cached prefix invalidates every turn (only within-turn caches).
  Keep the static SYSTEM playbook in `system` and move retrieved memory/vault to the tail (a message or
  a second breakpoint) so `[tools][static system]` survives across turns at 0.1x. The bigger cost lever.
- **Tune the tool-result cap** — `TOOL_RESULT_CHAR_CAP` (48k) is a first guess; watch the "capped …"
  log to see what actually trips it and adjust. Head/tail split too.
- **Tool-result lifecycle → vault (the real "layer")** — hot=full, warm=cached, cold=demoted-to-stub
  and written to the durable store, recalled via §5.9 auto-assembly. Context window as L1 cache, vault
  as RAM. Strictly better than placeholder-eviction (nothing lost). Scope deliberately post-memory.
