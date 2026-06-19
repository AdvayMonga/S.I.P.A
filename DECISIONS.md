# DECISIONS.md

Append-only log of non-obvious choices and *why*. Newest at the bottom. See `CLAUDE.md` for
when to append.

---

## 2026-06-13 — The verifier gates both workflow modes

**Decision.** The verifier (`VERIFIER.md`) runs in both flows, judging the change rather than
its author. Interactive work runs the **fast** profile (checks 1–4: build → typecheck → lint →
existing tests) as a pre-commit hook; the auto-builder runs the **full** profile on its branch.
`CLAUDE.md`'s "Verify before every commit" agreement points at the fast profile.

**Why.** The auto-builder's strongest gate is "existing tests pass" (`VERIFIER.md` §4), which
only means something if `main` was green when it branched. The interactive fast gate is what
keeps `main` green, so it's load-bearing for the autonomous gate — not a nicety. Same
deterministic core both ways; only the ceremony (branch + approval) differs.

## 2026-06-13 — Sandbox runtime deferred, but the seam is fixed now

**Decision.** Don't pick a sandbox product yet. Commit only to the *shape*: the sandbox is a
swappable backend behind the broker (`provision → seed → build → test → emit patch → destroy`).
When the autonomous phase arrives (last in the build order), start with one managed microVM
sandbox (current lean: **E2B** — real isolation, GA default-deny egress, Python SDK) and harden
only when there's a reason to. A fully-local runtime (microsandbox / self-hosted libkrun or
Firecracker, or a custom box) is the eventual target, not the start.

**Why.** By the build order the sandbox is only needed in the final autonomous phase — choosing
now means committing before anything it must contain exists. `sandbox.md` is a threat-model
checklist, not a hard requirement (see its header). Web verification (2026-06-13): Daytona's
default Sysbox shares the host kernel and its OSS self-host is plain Docker-in-Docker (fails the
isolation bar); Modal is real gVisor isolation but cloud-only with beta domain-egress; E2B
(Firecracker, Apache-2.0, mature egress) is the better managed bridge, microsandbox (libkrun,
Apache-2.0) the cleaner local endpoint. A stable broker seam makes "E2B now → local later" a
backend swap, not a rewrite.

## 2026-06-13 — M0 builds the real MCP server, not an in-process tool

**Decision.** The first Obsidian tool (`vault_create_note`) is a real MCP server (FastMCP) over
stdio from M0, with a minimal MCP host in the loop — not an in-process function. Honors
`VISION.md` invariant 4 ("every capability is an MCP server") from the first line.

**Why.** Chose to build the real extensibility seam up front rather than defer it. Trades a
bigger M0 (adds the host + stdio transport) for proving the actual architecture — the same seam
every future capability and the auto-builder target — end to end from day one.

## 2026-06-13 — Pre-commit hook deferred

**Decision.** No git pre-commit hook for now. The verifier's fast profile (build → typecheck →
lint → existing tests) still gates every commit — run before committing (by Claude during
interactive work) rather than enforced by a hook. Hook references removed from `VERIFIER.md`,
`siloop.md`, and `VISION.md`'s layout/CI.

**Why.** Solo + interactive, with Claude running the checks before each commit, makes the hook
redundant for the happy path. Its real payoff — a deterministic floor that doesn't depend on
diligence, which the auto-builder relies on for a green `main` — arrives with autonomy. Cheap,
easy add then: wire `.pre-commit-config.yaml` to the fast profile. Deferred, not dropped.

## 2026-06-13 — Vault git deferred past M0

**Decision.** The bot doesn't manage git for the Obsidian vault yet. M0's only mutation is
`vault_create_note`, which is non-destructive (fails if the note exists) and watched live in the
REPL. Vault git (`git init` + auto-commit per mutation) lands with the first destructive/surgical
op (`vault_append` / `patch` / `move` / `trash`) or the first unattended write (proactive timer,
phone) — whichever comes first.

**Why.** Invariant 1 ("every mutation undoable") is load-bearing once the bot edits or deletes,
or writes when you're not watching — there's no Ctrl-Z for a proactive multi-note edit, so git is
the undo + the audit log of what the bot did. While the only op is a watched, non-destructive
create, "just delete the stray note" suffices and git is avoidable complexity. Keep it in
`VISION.md` §6 as the design; realize it when destructive/unattended writes make it earn its keep.

## 2026-06-13 — Vault git activated in M1 (trigger condition met)

**Decision.** Vault git (`vault_git.py`: init-on-demand + auto-commit per mutation, local-only)
ships with M1, because M1 adds the first destructive/surgical ops (`append`/`patch`/`move`/`trash`).
This executes the deferral above — the named trigger ("first destructive op") is now met. Commit
happens in `server.py` (the sole mutation entry point), not in the pure `vault.py` ops.

**Why.** Directly follows the prior deferral; not a new judgment call. The manual-edit-frictionless
requirement (`VISION.md` §6, watcher auto-commit) is **not** in M1 — only the bot's own mutations
are committed for now; a debounced watcher for human edits comes later.

## 2026-06-13 — servers/ relocated to the repo root (out of src/bot)

**Decision.** Moved `src/bot/servers/` → top-level `servers/`, matching `VISION.md` §4. Import
path `bot.servers.obsidian` → `servers.obsidian`; `pyproject` packages both `src/bot` and
`servers`; the host spawns `python -m servers.obsidian.server`.

**Why.** An MCP server is an independent process the core reaches only over stdio — the core
never Python-imports it — so it shouldn't live *under* the `bot` package. M0 nested it for
packaging convenience; corrected now while there's a single server. Top-level placement is the
signal of independence; true per-server dependency isolation is deferred (`BACKLOG.md`).

## 2026-06-13 — Scheduler: vault-note definitions + data-side last-run; on-open trigger (M3)

**Decision.** Recurring tasks are a `scheduler` MCP server. Task **definitions** (prompt, cadence,
enabled) live in the vault note `_system/Scheduled.md` (user-visible/editable, versioned); **last-run
timestamps** live in `data/scheduler_state.json` (operational, gitignored). The **trigger** is the
loop at startup (runs due tasks via the host, pure MCP) — a stand-in for the daemon's timer source.
The `MCPHost` is generalized to spawn multiple servers (obsidian + scheduler) and route by tool name.

**Why.** Splitting definitions (vault) from last-run (data) honors "the store you see is a vault
note" while keeping the vault from churning on every run. On-open triggering needs no daemon and
works for "daily" via last-run timestamps even with intermittent use. Core never imports the
scheduler — it asks via MCP, so tasks stay out of core (invariant 5). The scheduler commits its
definition changes by importing `servers.obsidian.vault_git` (shared vault infra; flagged for
extraction in BACKLOG).

## 2026-06-13 — Semantic index: NumPy brute-force (not sqlite-vec), local fastembed, own server (M4)

**Decision.** Semantic recall is a separate `vault_search` server (`VISION.md` §5.7), independent of
obsidian. Embeddings: local **fastembed** bge-small (384-dim), behind an `Embedder` protocol (tests
inject a stub). Vectors stored as blobs in SQLite and searched **brute-force in NumPy** — not
`sqlite-vec` — because this Python (python-build-standalone via uv) is compiled without
`enable_load_extension`. Retrieval is **hybrid**: vector cosine + FTS5 keyword, fused with RRF.

**Why.** `sqlite-vec` is a loadable extension; the uv Python can't load it, and switching the
project Python is disruptive. NumPy brute-force is correct and fast at personal-vault scale (the
real constraint is the embed pass, not the cosine). `sqlite-vec`/LanceDB remain the scale path
(needs a different SQLite build). fastembed keeps embeddings on-device (local-first). Hybrid RRF
beats either channel alone — a synonym query with no shared words still ranks the right note.

---

## 2026-06-13 — `vaultfs` top-level package for shared vault infra

**Decision.** Extracted the vault filesystem primitives (`vault.py`) and local git (`vault_git.py`)
out of the obsidian server into a new top-level package, `src/vaultfs/` (importable as `vaultfs`).
All capability servers — obsidian, scheduler, vault_search, and future ones (memory) — now import
*downward* from `vaultfs`; no server imports another server. The obsidian FTS5 keyword index
(`servers/obsidian/index.py`) stays in obsidian (it's obsidian's own index, not shared).

**Why.** Three servers were reaching sideways into the obsidian server's modules
(`scheduler → vault_git`, `vault_search → vault`), which broke the plug-in independence the
architecture promises (`VISION.md` invariant 4): obsidian was acting as a hidden shared library, a
layering inversion where infra was owned by a sibling capability. The memory server (M5) would have
been the third such consumer, calcifying the tangle — better to extract before it lands than untangle
four servers later. The vault is the substrate every capability is built around, so its primitives
belong in foundational shared infra, not inside one capability.

**Placement nuance.** `vaultfs` lives under `src/` next to the routing core `bot`, so it reads as
core-level shared infra — but it is **not inside `bot`**, and `bot` never imports it. The turn-routing
core stays vault-ignorant, preserving the spirit of invariants 4/5 while giving every server one
clean shared dependency.

## 2026-06-13 — `embedding` top-level package; recall-tier-only vectors; `done` needs a tool

**Decision (extraction).** `Embedder` + `FastEmbedEmbedder` moved out of
`servers/vault_search/embed.py` into a new top-level package `src/embedding/` (importable as
`embedding`), parallel to `vaultfs`. Both `vault_search` and the new `memory` server now import the
embedder *downward* from it; neither imports the other.

**Why.** Same rule as the `vaultfs` extraction: the memory server (M5) needs the *same* embedder
`vault_search` uses, and importing it from `servers.vault_search` would have recreated the exact
cross-server coupling we just removed. Shared infra goes in a shared package, not inside a sibling
capability. The ~5-line cosine stays duplicated in each store — a shared vector-store abstraction
over two different schemas (chunks vs. memory entries) would be premature at two consumers.

**Decision (vectors).** Only recall-tier entries are embedded; profile entries store `vec = NULL`.
**Why.** Profile is returned wholesale by `memory_get_profile`, never vector-searched, so embedding
it is wasted compute. `memory_recall` is vector-only over recall entries (design's stated M5 scope).

**Decision (`done` status).** Added a `memory_complete_task(id)` tool not in the design's tool table.
**Why.** The design's schema mandates `status='done'` for tasks, but its tool list gave no way to
reach it — `forget` deletes and `update` supersedes, neither marks done. Without a tool, `done`
would be unreachable dead state. `memory_complete_task` is the minimal realization of the status the
schema already requires; it drops a task from `list_open_tasks` while keeping it as history.

## 2026-06-14 — Retrieval becomes pushed; the system prompt is now dynamic per turn

**Decision.** Context assembly v2 (M6, §5.9) flips retrieval from **agentic** (model chooses to call
`memory_recall`/`semantic_search`) to **pushed**: `run_turn` calls `assemble_context` once per turn
and injects profile + top-k memory + top-k vault into the system prompt. The search tools stay
available for deep dives. So the system prompt is **rebuilt every turn** (it keys off the user
message) — not the former static constant.

**Why.** This is the piece that makes the bot *feel* like it knows you — the relevant slice of the
durable stores lands in working memory automatically, no tool call needed (the 3-layer-memory glue).

**Consequence to know.** A per-turn dynamic system prompt is intentional, not a bug — don't "fix" it
back to a constant. It does defeat Anthropic prompt caching on that block; base SYSTEM is small so
the cost is minor, and a static/dynamic cache split is deferred (`BACKLOG.md`). Budget is char-based
(profile-first, remainder split memory/vault); a real tokenizer is the later upgrade.

## 2026-06-14 — Conversation object replaces the raw history list; in-session compaction

**Decision.** `run_turn` now takes a `Conversation` (messages + rolling `summary`) instead of a raw
`list`. When real user turns exceed a threshold, `maybe_compact` LLM-summarizes the older turns into
`summary` and drops them, keeping the most recent turns verbatim. The summary enriches the retrieval
query and is injected as `# Conversation so far`.

**Why.** Bounds the context window for long sessions (what Claude Code does internally) and resolves
follow-ups ("the next step?") by retrieving against conversation state. It's layers 1–2 of the
3-layer memory model (working memory + compaction); M6 was layer 3 (the stores).

**Pairing-safe cut.** Anthropic requires each `tool_result` to follow its `tool_use`. Compaction
cuts only at *real user turns* (role user, string content), so the kept window never starts on an
orphaned `tool_result`. Tested.

**Scope line.** The summary lives in memory for the session only — persisting it across process
restarts (and optionally distilling it into the memory store as an `episode`) needs a real session
lifecycle and belongs with the daemon (`BACKLOG.md`).

## 2026-06-14 — Daemon: one serialized router, many sources; on-open fires once

**Decision.** The REPL becomes a long-lived `Daemon`: one `Conversation` + one `asyncio.Queue`,
processed by a single `_router` that runs turns one at a time. Inputs arrive as `Event`s from
pluggable `Source`s — `StdinSource` (the REPL), `SocketSource` (Unix socket for external clients),
`TimerSource` (wall-clock). Each event carries a `respond` callback so a reply goes back to *its*
origin. `_make_handler` wires the router to `run_turn`.

**Why.** Serial-by-construction means all sources share one brain without locking or races. Sources
are the extension seam for desktop/Telegram (just add a `Source`) — mirroring how MCP servers are
the seam for capabilities. A handler exception becomes an `[error]` reply, never killing the daemon.

**on-open under a persistent process.** `on-open` tasks are "always due"; a never-closing daemon
would re-fire them every timer tick. So `_make_fire_due` fires on-open tasks only on the **first
(startup) tick**; daily/weekly fire whenever genuinely due. With a daemon, "open" = startup.

**Shutdown.** `StdinSource` raises `ShutdownSignal` on EOF; the TaskGroup unwinds and `cli` catches
it with `except*`. Headless deployments simply omit `StdinSource`.

**Deferred:** token budgeting/cost rollups and session-summary persistence (`BACKLOG.md`).

## 2026-06-15 — Auto-builder (siloop) will run on the Claude Max subscription, not the API

**Decision.** When the self-improving loop / auto-builder (`siloop`) is built, its coding executor
routes through **Claude Code / the Claude Agent SDK authenticated with the user's Max subscription**
(OAuth via `claude setup-token`), not the pay-per-token API. SIPA's conversational turns stay on the
API (`AnthropicProvider`) for now.

**Why.** The raw API can't draw on a subscription — it's always separately metered. But Pro/Max
plans get a monthly Agent SDK credit covering the Agent SDK, `claude -p`, and third-party apps built
on it. Coding/agentic work is exactly what Claude Code is for and is the expensive, bursty load — so
billing it to the subscription instead of API tokens is the real cost win, landing where the spend
actually is.

**Caveats to honor when building it.** (1) If `ANTHROPIC_API_KEY` is set in that environment it
*overrides* the subscription and silently drains API balance — keep the two paths' envs separate.
(2) The subscription credit is finite with no fine-grained spend controls, so the loop cap + cost
visibility matter more there. (3) Moving SIPA's *chat* turns onto the Agent SDK is possible (the
credit covers third-party apps) but is a re-architecture — the Agent SDK runs its own agent loop —
so it's deferred, not a drop-in for our hand-built loop. Sources: Claude Code + Agent SDK auth docs.

## 2026-06-17 — Dashboard drag: react-grid-layout v1.5 + a `process` shim

The customizable dashboard uses **react-grid-layout 1.5** (not the 2.x rewrite). 2.x dropped the
flat `WidthProvider`/`draggableHandle` API and ships an immature `legacy` shim; v1.5 is the mature,
battle-tested API and is the right call for a project that needs to just work.

**The drag bug that ate a session:** tiles wouldn't drag — mousedown selected text instead.
Root cause was *not* our code (wiring, StrictMode, and handle were all correct). react-draggable
(bundled in RGL) has a debug `log()` that reads `process.env.DRAGGABLE_DEBUG`; with no Node
`process` global in the browser it threw `ReferenceError: process is not defined` inside
`handleDragStart`, *before* `preventDefault()` — so every drag aborted and the browser selected
text. Fix: shim `window.process = { env: {} }` in `index.html` (runs before any module) plus a Vite
`define` for the same key. Lesson: when a library's event handler throws, the symptom (text
selection) looks like a CSS/handle problem but is really the handler dying mid-flight — check the
console early.

Also removed `React.StrictMode` (main.tsx): it wasn't the cause here, but RGL's reliance on the
deprecated `findDOMNode` makes StrictMode's double-mount a known source of drag flakiness, so it
stays off while we use RGL.

## 2026-06-17 — Dashboard telemetry rides one typed channel, not a separate transport

**Decision.** Live module state (token cost, background-agent status, scheduler fires) flows over the
**existing M16 push/`:subscribe` channel**, not a second socket connection. Every push payload gets a
typed envelope — `{type: "chat" | "telemetry", topic, ...}` — and the desktop routes on `type`
(then `topic`) to the owning module. We reserve `topic` now but ship with every subscriber receiving
every event and filtering client-side; topic-filtered *subscriptions* (`:subscribe <topic>`) are a
later evolution on the **same** transport, added only when a second consumer with divergent needs
appears.

**Why.** The expensive-to-change thing long-term is the **envelope schema, not the socket count**.
A second transport doubles the failure surface (two reconnect paths, two liveness checks, split
ordering between "the bot said X" and "cost is now Y") for isolation we don't need at this scale:
telemetry here is low-frequency (per-turn cost, per-tick scheduler, agent transitions), so there's
no flood that could starve chat on a shared serialized stream. The dashboard's growth adds *tiles*,
not *clients* — it's still one desktop app on one socket routing by type. The genuinely future-proof
design is topic-tagged events on one transport with optional subscription filters, and that is a
strict superset of the typed-envelope approach — we grow into it, never rewrite toward it. Getting
the envelope typed now (vs. an untyped blob) is what keeps that path open.

## 2026-06-18 — Desktop live state: fetch a snapshot on mount, then apply push deltas

**Decision.** A desktop module that mirrors slow-changing server state (the **threads** switchboard
today) **fetches a full snapshot on mount** via a request/response command (`list_threads`, retried
until the daemon is reachable), then keeps it current with **pushed deltas** (`sipa-telemetry`
events). It does *not* rely on the daemon's on-subscribe broadcast to seed initial state.

**Why.** The on-subscribe broadcast (daemon pushes the thread list when a client `:subscribe`s) races
the frontend: Tauri's `app.emit` can fire before React's async `listen()` is active, so the very
first snapshot is silently dropped — the panel starts empty and only fills on the next state change
(e.g. "+ new thread"). A request/response fetch has no such dependency on listener timing, and the
retry also covers the cold-start case (daemon not up yet). This is the standard live-view pattern
(GET current state + subscribe to changes) — one state store seeded by the fetch and updated by
deltas, not two sources of truth. The rejected alternative — keep a single push source but only start
the stream after listeners attach — is more fragile in React+Tauri (guaranteeing "listeners active"
before signaling ready is itself racy).

**Scope.** Only **threads** needs this: fast-changing state (cost, replies, approvals) self-heals on
the next turn/interaction, so a missed initial push there is invisible. The on-subscribe broadcast is
kept (it's still correct for reconnects once listeners are mounted) — the fetch just makes initial
state reliable.

**Deferred (`BACKLOG.md`).** If more slow-changing modules appear (e.g. the scheduler tile), unify
the per-topic fetches into one `:snapshot` command returning all live module state at once, rather
than N bespoke fetches. The `list_threads` fetch is the seed of that pattern.

## 2026-06-18 — Executed the `:snapshot` unification (scheduler tile)

**Decision.** The scheduler tile was the second slow-changing module, so — per the note above —
`:threads`/`list_threads` is replaced by `:snapshot`, returning `{threads, scheduled}`. Threads and
Scheduler both seed from it on mount (retry until the daemon is up). Rather than a new push topic,
the read-only Scheduler tile **re-fetches `:snapshot` whenever cost telemetry arrives** — a completed
turn is the only thing that can have changed the schedule (model scheduled/cancelled, or a task
fired) — so it stays current with no extra backend wiring. The daemon stays scheduler-agnostic: a
`scheduled()` callable (host → `list_scheduled_tasks`) is injected into `SocketSource`, mirroring how
`fire_due` is injected into the timer. Tile is display-only; interactive edits deferred (`BACKLOG`).

## 2026-06-18 — Trim the per-turn context envelope (caching + gated retrieval)

**Problem.** Every chat turn — even "hello" — carried a ~6k-token fixed envelope: the 32-tool
schemas (~1600 tok, byte-stable) plus an always-on context block (profile + top-5 memory + top-5
vault, ~1500 tok) with no relevance filter.

**Decisions.**
- **Cache the tool prefix, not the system.** Tools are byte-stable every turn → an ephemeral
  `cache_control` breakpoint on the last tool caches the whole tool prefix (~90% off on repeat).
  The system prompt is *not* cached: the context block is query-dependent, so it changes every
  turn and would never hit. (`provider.py`)
- **Profile = identity (always on); retrieval = query-driven (skippable).** Greetings/acks
  (`is_trivial`) have no real query, so they skip memory+vault retrieval but keep the profile —
  honouring VISION §5.9 ("just knows you") while dropping the noise. (`context.py`, `loop.py`)
- **Gate on similarity, and missing score = keep.** Memory gates on its cosine `score`; vault
  gates on a newly-exposed vector cosine `sim` — its RRF `score` is rank-based (max ~0.033) and
  useless for absolute relevance, so the raw cosine (previously computed in `_vector_ranks` then
  discarded) is now surfaced. A row lacking a score is kept: only *known*-irrelevant rows drop.
- **Thresholds start at 0.55, tunable.** bge-small-en-v1.5 cosine baseline runs high (unrelated
  text ~0.5), so 0.55 only drops clear misses. Not empirically calibrated yet — `MEM_MIN_SCORE` /
  `VAULT_MIN_SCORE` in `context.py` are the knobs. Known edge: a pure-keyword hit outside the
  vector pool has `sim`=0 and is gated out (acceptable; relevance trusts vector similarity).

## 2026-06-18 — Context-assembly v2: query transformation, not rerank (BACKLOG §51b)

**Problem.** Retrieval embedded the user's literal words. Vague follow-ups ("what about the second
one?", "and the next step?") retrieved garbage — the pronoun never resolved to a referent. The
earlier mitigation (prepend `summary[-500:]` to the query) was empty before the first compaction
(the common 2–3-turn case) and *diluted* the query rather than *resolving* it.

**Decisions.**
- **Query transformation over reranking.** BACKLOG calls rerank "the single biggest jump," but
  rerank only reorders an existing candidate pool — with a ~7-note vault and k=5 there is nothing to
  reorder. Its leverage scales with corpus size; it's premature today. The failure here is the
  *query*, not the *ranking*, and that fails at any scale → query transformation first.
- **LLM rewrite, gated.** `query.py:rewrite_query` resolves a follow-up into a standalone query via
  the rolling summary + recent turns. To keep the extra model call off most turns, `_needs_rewrite`
  fires only with prior history AND a dependent-looking message (pronoun/deixis marker or ≤6 words).
- **Retrieval-only, degrade to raw.** The rewrite is never shown and never appended to `messages`,
  so a bad rewrite costs a little recall, never conversation integrity. Provider error / empty
  rewrite → raw message. Trivial turns skip it (they don't retrieve).

## 2026-06-18 — Adversarial claim-verification for deep research (`verify_claims`)

**Why code, not a playbook line.** Verification is the one research step where prompt-trust is
self-defeating: a model checking its own findings is biased to confirm them. The value is
*independence* + *adversarial framing*, and those can't be left to the model to remember — they're
locked in code. `src/bot/verify.py` + a `verify_claims` tool.

**Decisions.**
- **Reuse the sub-agent fan-out.** Each skeptic is an isolated `run_subagents` loop with full tools
  (incl. web) — fresh context that sees only the claim, never the reasoning that produced it. No new
  fan-out machinery; verification is just a specialized use of it.
- **Skeptical aggregation.** `VOTERS=2` independent skeptics per claim. `refuted` if *any* refutes,
  `supported` only if *all* confirm, else `uncertain`. A missing/garbled verdict line parses to
  `uncertain`. Research notes should err toward flagging, not asserting — false-but-confident is the
  failure we're buying against.
- **Top-level only.** Offered alongside `delegate` (only when `allow_delegate`), so a skeptic
  sub-agent (which runs `allow_delegate=False`) can't recurse into more verification. Same 1-level
  rule as delegation.
- **Cost is real and dialed by `VOTERS`.** claims × voters full sub-agent research loops — opt-in
  deep research only, and the playbook verifies *key* claims, not every sentence.
