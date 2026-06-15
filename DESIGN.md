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
| Context assembly v2 | built | [context-assembly.md](design/context-assembly.md) | Per-turn pushed retrieval: auto-inject profile + top-k memory + top-k vault (provenance-tagged, one char budget) into the system prompt. Retrieval goes agentic → automatic. |
| Conversation memory | built | [conversation-memory.md](design/conversation-memory.md) | The within-session HANDOFF: `Conversation` (messages + rolling summary); compaction folds old turns into the summary when the window grows; summary enriches retrieval + is injected. |
| Daemon + event router | built | [daemon.md](design/daemon.md) | Always-on core: one serialized router (queue + `Conversation`) fed by event sources — stdin (REPL), Unix socket (external clients), wall-clock timer (fires due scheduled tasks). Token/cost logging. |

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
