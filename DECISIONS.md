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
