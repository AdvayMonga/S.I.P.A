# DESIGN.md

Index of feature designs. One blurb + status + link per feature. **No design content lives
here** — the full design for each feature is in `design/<feature>.md`. This file is the table of
contents; keep it that way.

Status: `planned` · `building` · `built`.

| Feature | Status | Design doc | Blurb |
|---|---|---|---|
| Obsidian server | built | [obsidian-server.md](design/obsidian-server.md) | The ten `vault_` tools (act on the vault by path) + vault git + write-path validation + FTS5 index. |
| Scheduler | built | [scheduler.md](design/scheduler.md) | Recurring tasks (vault-note store) + on-open trigger; multi-server host. |
| Semantic index | built | [semantic-index.md](design/semantic-index.md) | `vault_search` server: chunk + embed + hybrid (vector + FTS5) RRF recall by meaning. |
| Memory server | built | [memory-server.md](design/memory-server.md) | `memory` server: profile + recall tiers in one SQLite store; vector-only recall; mechanical consolidation. Separate from the vault. |
| Web search | built | [web-search.md](design/web-search.md) | `web` server: `web_search` + `web_fetch` over a swappable `WebBackend` (Tavily today). Current/external info → sourced research notes. Spawns only when keyed. |
| Local files + vision | built | [local-files.md](design/local-files.md) | `fs` server (`read_file`/`list_dir`/`read_image`, scoped to configured roots) + host passes image content so the model can see images. Adaptive thinking enabled. |
| Sub-agents | built | [sub-agents.md](design/sub-agents.md) | `delegate` (parallel fan-out, cap 5) + `delegate_background` (detached worker → ping on done). Isolated loops, 1-level. |
| Code execution | built (interactive) | [code-execution.md](design/code-execution.md) | `exec` server (`run_shell`, scoped to `EXEC_ROOT`, off by default) + approval round-trip (`ask`) — interactive asks, unattended denied. Sandbox is later. |
| Context assembly v2 | built | [context-assembly.md](design/context-assembly.md) | Per-turn pushed retrieval: auto-inject profile + top-k memory + top-k vault (provenance-tagged, one char budget) into the system prompt. Retrieval goes agentic → automatic. |
| Conversation memory | built | [conversation-memory.md](design/conversation-memory.md) | The within-session HANDOFF: `Conversation` (messages + rolling summary); compaction folds old turns into the summary when the window grows; summary enriches retrieval + is injected. |
| Daemon + event router | built | [daemon.md](design/daemon.md) | Always-on core: one serialized router (queue + `Conversation`) fed by event sources — stdin (REPL), Unix socket (external clients), wall-clock timer (fires due scheduled tasks). Token/cost logging. |
| Desktop app | built (basic) | [desktop.md](design/desktop.md) | Extremely basic Tauri v2 shell: chat UI → `ask` command → daemon Unix socket. The front-end seam. |
| Concurrent chats | planned (M18) | [concurrent-chats.md](design/concurrent-chats.md) | The switchboard: daemon's one serial conversation → a flat pool of up to 5 concurrent chat threads. One focused (chat module), rest in the panel as status boxes; swap to switch; Stop/Resolve per thread; results wait quietly, continuity via shared memory. |
| Cloud presence | planned (sketch) | [cloud-presence.md](design/cloud-presence.md) | Sketch: dumb always-on relay (outbox + timer) for reliable reminder delivery; brain stays local. |

---

### Conventions

- **When to add a row.** A feature earns a `design/<feature>.md` (and a row here) when it's
  bigger than a `PLAN.md` task can carry — e.g. semantic index, memory, the self-improving loop,
  the sandbox. Small slices live in `PLAN.md` only.
- **Naming.** `design/<feature>.md`, kebab-case after the feature
  (`design/self-improving-loop.md`, `design/sandbox.md`, `design/semantic-index.md`).
- **As-built.** Each design doc is revised to reflect what was actually built. The transient
  build plans (`siloop.md`, `sandbox.md`) are superseded by their `design/` docs and then deleted
  (carry their invariants/contracts across first — see `CLAUDE.md` file map).
