# VISION.md — Personal Bot Base Layer

## 0. Purpose

The foundation for a personal AI bot that grows over time. First capability: an Obsidian vault as durable memory. Production grade, not a prototype. Every future capability plugs in without touching the core. This is the spec, not a schedule. Build order is dependency-driven (Section 10).

---

## 1. Principles (invariants)

1. **Stores are canonical and reversible.** Never lose data. Every mutation is undoable.
2. **The brain is stateless per turn.** All durable state lives in the stores. The process can be killed and restarted with no loss.
3. **The core runs as an always-on local daemon.** It holds the loop, the MCP host, the servers, and the stores. Front-ends are clients of it, not containers for it.
4. **Every capability is an MCP server.** Adding a power means adding a server, never editing the core. Sub-agents are servers too.
5. **Input is an event, not just a user message.** The loop handles an incoming event, which may be a human message, a timer, or a webhook. Proactive behavior never requires a core change.
6. **The brain is provider-agnostic.** The model sits behind a `ModelProvider` interface. Claude API default, local model swappable in by config.
7. **Agent memory is separate from the vault.** The vault is authored knowledge. Agent memory is the bot's model of you and its operational state. Distinct stores, distinct lifecycles.
8. **Store and index are separate.** Each store is the source of truth. Indexes are derived and rebuildable.
9. **Local-first.** Personal data stays on the machine by default. Anything leaving the device is opt-in.
10. **Fail safe, typed, observable.** Tool errors degrade gracefully and never corrupt a store. No untyped public functions. Every turn and tool call is logged with a trace id and cost.

---

## 2. Architecture

```
Clients          Desktop app (primary, Mac) and phone (Telegram). Connect over a local socket.
   |  socket
Daemon           Always-on local service. The hub.
   |  - Event router: turns client messages, timers, and webhooks into events
   |  - Agent loop: handles an event, behind a ModelProvider (Claude default, local swappable)
   |  - MCP host: connects servers, aggregates tools, routes calls
   |
Tool layer       MCP servers, one per capability (sub-agents included):
   |               obsidian | vault-search | memory | research | daily-log
   |
Stores           Vault (markdown knowledge) + Agent memory (distilled), each with its own index.
```

The hub is the daemon, not the app. Close the app and the daemon keeps running: timers still fire, the phone channel still works, and every source shares one brain and one memory. The vault has two access paths: mutate by path via `obsidian`, recall by meaning via `vault-search`. Agent memory has its own server.

---

## 3. Tech stack

`uv` for env and deps. Pin major versions.

| Concern | Choice |
|---|---|
| Language | Python 3.12+. MCP is language-agnostic, so any server can be rewritten in Go/Rust later without touching the core. |
| Model brain | `ModelProvider` interface. Claude via `anthropic` SDK default; local model (Ollama) swappable. |
| MCP | official `mcp` Python SDK (FastMCP for servers, client for the host). stdio transport, local. |
| Daemon transport | local websocket between daemon and client front-ends. |
| Desktop app | thin native shell (Tauri or webview) rendering a web chat UI. Global hotkey, menu bar, notifications, launch at login. |
| Vector store | SQLite + `sqlite-vec`. LanceDB if it outgrows that. |
| Keyword | SQLite FTS5 (BM25), same DB file. |
| Embeddings | pluggable. Local `fastembed` (bge-small) default; hosted (Voyage/OpenAI) optional. |
| Markdown | `python-frontmatter` + a small wikilink parser. |
| File watching | `watchdog`. |
| Vault versioning | `git`, local only. Auto-commit every mutation. Never pushed to a remote. |
| Tests / lint / types | `pytest`, `ruff`, `pyright`. |

---

## 4. Repository layout

```
personal-bot/
  pyproject.toml  .env.example  Makefile  VISION.md

  src/bot/
    config.py            # typed Settings
    logging.py           # structlog, trace ids
    daemon.py            # always-on service: starts host, servers, event router, socket
    core/
      loop.py            # stateless agent loop (handles an event)
      provider.py        # ModelProvider: Claude API, local model
      host.py            # MCP host: connect servers, aggregate tools, route calls
      router.py          # event router: clients + timers + webhooks -> events
      context.py         # context assembly: profile + memory + vault -> bounded block
      budget.py          # token budgeting, history trimming
      cost.py            # token + cost accounting

    sources/
      base.py            # EventSource protocol (client and in-process)
      socket.py          # local websocket server for client front-ends
      telegram.py        # phone channel
      timer.py           # scheduled events (proactive)
      webhook.py         # inbound triggers (proactive)

  app/                   # desktop app: native shell + web chat UI, client of the daemon
  servers/
    obsidian/            # vault.py (path-safe fs, atomic writes, git), links.py
    vault_search/        # index.py, chunk.py, embed.py, graph.py, watch.py
    memory/              # store.py, recall.py, consolidate.py
    research/  daily_log/  _template/

  tests/                 # servers/, core/, evals/ (retrieval golden set + MCP eval XML)
  data/                  # gitignored: index.db, memory/, logs/
```

The vault lives in its own private git repo at a configured path, outside this repo.

---

## 5. Components

### 5.1 Daemon and transport
A long-lived local service (`launchd` on Mac: start on login, stay up). It owns the host, the servers, the stores, the event router, and the local socket. Front-ends connect over a local websocket. In-process sources (timer, webhook) run inside it. One running brain and memory for all front-ends.

### 5.2 Event router and sources
`EventSource` protocol: produce events, deliver replies. Two kinds. Client sources arrive over the socket (desktop app, phone). In-process sources run inside the daemon (timer, webhook). The router normalizes all of them into one `Event` type and feeds the loop. The loop never knows the origin.

### 5.3 Agent loop
Stateless. Given history and an event, call the model through `ModelProvider`, run any tool calls, feed results back, repeat until a final answer. Tool errors return as `is_error` tool results so the model can recover. Retry model calls with backoff. Enforce a token budget; durable state goes to the stores, not the context window. Emit trace id and cost per turn.

### 5.4 Model provider
One interface: messages + tools -> response + usage. `AnthropicProvider` (default) and `LocalProvider` (Ollama). The loop and servers target the interface, so switching is a config change.

### 5.5 MCP host
Spawns servers over stdio, aggregates their tools into the model's tool list, routes each call to its server. A crashed server takes only its capability offline; reconnect with backoff. Server list comes from config, so adding one is config, not code.

### 5.6 Obsidian server (act on the vault by path)
```
vault_list_notes(folder?, limit, cursor)     readOnly, idempotent
vault_read_note(path)                          readOnly
vault_search_text(query, limit)               readOnly   # exact keyword/regex
vault_resolve_link(title)                      readOnly   # find path by title, for linking
vault_get_backlinks(path)                      readOnly
vault_create_note(path, content, frontmatter?)            # fails if exists
vault_append(path, content, under_heading?)               # non-destructive
vault_patch_section(path, heading, content)               # surgical edit
vault_move_note(old, new)                      idempotent # updates inbound links
vault_trash_note(path)                         destructive # soft delete to /_trash
```
Safety: path traversal confined to the vault root; extension whitelist; atomic writes (temp + rename); git auto-commit after every mutation; no hard deletes.

Write-path validation (every create/append/patch): resolve any `[[links]]` against the vault and flag or auto-correct unresolved targets via `vault_resolve_link`; validate frontmatter as well-formed YAML; check table column counts are consistent. Malformed output is rejected before it lands, so the bot never quietly writes a broken link or table.

### 5.7 vault-search server (recall from the vault by meaning)
```
semantic_search(query, k, filters?)   readOnly   # hybrid retrieval: chunks w/ path, heading, score
expand_context(paths, hops=1)         readOnly   # link-graph expansion
index_status()                        readOnly
reindex(paths?)                                  # usually automatic
```
Index: heading-aware chunking; pluggable embeddings (model id + dim stored with vectors); `sqlite-vec` for vectors and FTS5 for keyword; hybrid fusion via Reciprocal Rank Fusion, optional rerank later; link graph parsed into an edges table; incremental reindex via `watchdog` keyed on file hash/mtime. Embedding is a precomputed write-time cost; a query is one embedding plus a nearest-neighbor lookup.

### 5.8 memory server (cross-session agent memory, separate from the vault)
```
memory_get_profile()                   readOnly    # small, always-injected tier
memory_recall(query, k, filters?)      readOnly    # episodic/semantic retrieval
memory_list_open_tasks()               readOnly    # working memory across sessions
memory_remember(content, kind, keys?)              # distill a durable fact or summary
memory_update(id, content)             idempotent  # supersede, mark old stale
memory_forget(id)                      destructive # soft delete
```
Two tiers in one store. **Core profile**: small, capped, injected every turn (preferences, standing instructions, key entities, and a **house-style note**: your folder layout, tag taxonomy, note-naming, and which plugins you use, seeded by you and refined as the bot observes the vault). The house-style note is what makes the bot write in your conventions rather than generic ones. **Recall store**: episodic summaries and facts, retrieved top-k, reusing the same embed/index machinery in a separate collection. Kinds: `fact`, `preference`, `instruction`, `episode`, `task`. Lifecycle: distill at session end (and on "remember this"), never store raw transcripts; **consolidate and prune** is a first-class job (merge duplicates, supersede stale, keep the profile under cap, newest-wins on conflict). May reference vault notes by path; durable knowledge can be promoted into the vault.

### 5.9 Context assembly
Per turn, build one token-capped block from three sources, with provenance so the model can cite and link: always inject the core profile; retrieve top-k agent memory; retrieve top-k vault notes, optionally one hop along the graph. Never dump a whole store.

### 5.10 daily-log and research (flows)
**daily-log**: distill a conversation into `Daily/YYYY-MM-DD.md` under stable headings, linking mentioned people and projects via `vault_resolve_link`. Append is deduped. **research**: web search/fetch synthesized into linked vault notes with sources.

### 5.11 Desktop app
The primary human surface on Mac. A thin native shell (Tauri or webview) rendering a web chat UI, connecting to the daemon over the local socket. Provides global hotkey, menu bar presence, notifications, and launch at login. Implements the client side of `EventSource`. UI is swappable; the core is untouched.

---

## 6. Stores

- **Vault**: markdown in its own folder, `git init`ed locally for history. Canonical. Auto-committed per mutation; recover with `git revert`/`checkout`. **Your manual Obsidian editing stays frictionless — you never run git;** a watcher auto-commits your manual edits on a debounce so they get the same undo/audit as the bot's writes. **Local-only: the vault is never pushed to GitHub or any remote.** Offsite backup, if wanted, is via local means (Time Machine, an external or encrypted drive), not a code-hosting service.
- **Agent memory**: distilled entries in `data/memory/`, separate from the vault, versioned, machine-managed (written, consolidated, pruned). No raw transcripts.
- **Indexes**: vault index in `data/index.db` and the memory index, both derived and rebuildable from their stores.
- **Conversation logs**: `data/logs/`, operational only. Durable signal is distilled into memory.

---

## 7. Cross-cutting

- **Observability**: structlog JSON, trace id per turn through tool calls, per-turn and per-day cost.
- **Errors**: recoverable tool errors, model-call retries with backoff, server crashes isolated. Never a partial write.
- **Testing**: unit tests per tool against a temp vault; loop integration tests (live model tests opt-in); a retrieval eval harness with a golden set measuring recall@k, run in CI; per-server MCP eval XML.
- **CI**: ruff, pyright, pytest, retrieval eval on every push.

---

## 8. Security and privacy

- **Storage privacy (default, fully local)**: vault, indexes, memory, logs all on the machine. The vault's git history is local only and never pushed to GitHub or any remote. Local embeddings so even embedding text never leaves.
- **Inference privacy**: a hosted model receives the per-turn context. For zero data leaving, set the provider to local. Confirm current API data terms in the provider's own docs.
- **Transport privacy**: choose the human channel for sensitivity (Signal private, SMS not, Telegram between).
- **Baseline**: secrets in env or keychain, never logged; path sandboxing and size/rate guards; soft-delete only, no hard deletes.

---

## 9. Extensibility contract

To add a capability: copy `servers/_template`, implement tools (prefixed action names, Pydantic in/out schemas, MCP annotations `readOnlyHint`/`destructiveHint`/`idempotentHint`/`openWorldHint`, actionable errors), add it to config, write tests and an eval XML. No core changes.

**Sub-agents** are this same pattern: a specialized agent is an MCP server whose tool runs its own loop and returns a result. Multi-agent stays inside the capability seam.

---

## 10. Capabilities and build order

Dependency order, not a schedule. Each "done when" defines correct.

- **Foundation** — repo, config, logging, CI, `ModelProvider`, `_template`. *Done:* `make check` passes, empty loop starts and exits.
- **Daemon + agent core** (Foundation) — daemon, socket, event router, loop, host, budgeting, cost. *Done:* a multi-turn conversation runs through the daemon over the socket with cost logged.
- **Obsidian server** (core) — `vault_` tools, path safety, atomic writes, git, write-path validation. *Done:* creates/appends/patches notes; links resolve and malformed frontmatter/tables are rejected; every mutation is a commit; traversal and hard-delete blocked by tests.
- **Keyword retrieval** (obsidian) — FTS5, `vault_search_text`, basic context injection. *Done:* "what did I note about X" pulls real notes with citations.
- **Semantic vault index** (keyword) — chunking, embeddings, sqlite-vec, hybrid RRF, incremental watcher, graph expansion. *Done:* recall@k beats keyword on the golden set; graph expansion returns linked notes.
- **Memory server** (core; shares index machinery) — two tiers, `memory_` tools, distillation, consolidation/prune. *Done:* recalls across sessions; profile stays under cap; consolidation merges and supersedes.
- **Context assembly v2** (memory + semantic index) — profile + memory + vault fused under one budget with provenance. *Done:* a fresh session has continuity from memory and answers grounded in notes, both cited.
- **Desktop app** (core) — native shell + web chat UI client over the socket, hotkey, menu bar. *Done:* you talk to the daemon from a Mac window while working; closing it leaves the daemon running.
- **Event sources** (core) — Telegram client, plus the socket already in place. *Done:* full conversation from your phone, sharing the same brain.
- **Proactive triggers** (event sources) — timer and webhook sources. *Done:* a scheduled event (e.g. a morning summary) runs on its own and reaches you.
- **daily-log and research** (obsidian) — *Done:* "log my day" makes a linked dated note; "research X" makes a linked note set with sources.
- **Sub-agents** (core; server per the contract) — *Done:* the bot delegates to a sub-agent server and uses its result, no core change.
- **Local model option** (core) — `LocalProvider`. *Done:* runs fully local with no conversation data leaving.
- **Hardening** — observability review, evals gating CI, local backup/restore drills for both stores. *Done:* runs as a daemon, evals gate merges, restore from a local backup verified end to end.

---

## 11. Definition of done (production checklist)

- [ ] Typed, pyright clean. Tests for every tool and the loop. Retrieval eval in CI.
- [ ] Structured logging with trace ids; per-turn cost tracked.
- [ ] Secrets in env/keychain; nothing sensitive logged.
- [ ] Model accessed only through `ModelProvider`; local provider runs end to end.
- [ ] Every vault mutation atomic and a git commit; no hard deletes in any store.
- [ ] Agent memory separate from the vault, consolidated and pruned, versioned.
- [ ] Both indexes rebuildable from their stores; verified.
- [ ] Daemon survives any single front-end closing; servers crash-isolated.
- [ ] Restore-from-backup drill passes for vault and memory.

---

## 12. Open decisions

1. **Model provider**: Claude API (capability) vs local (full inference privacy). Interface keeps both open.
2. **Desktop shell**: Tauri vs webview vs native SwiftUI.
3. **Embeddings**: local bge (privacy) vs hosted (quality).
4. **Memory consolidation**: prune cadence and profile size cap.
5. **Promotion policy**: when agent memory gets promoted into the vault.
6. **Rerank**: add only if precision is weak. **Vector store**: sqlite-vec until it must scale to LanceDB.
