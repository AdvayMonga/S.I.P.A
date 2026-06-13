# CLAUDE.md

Build-time guidance for working in this repo. This file is **advisory** — it nudges, it
doesn't enforce. The human reviews every diff; that review is the enforcement.

> **Project:** S.I.P.A. — a personal AI bot that grows over time. An always-on local daemon
> where every capability is an MCP server, with an Obsidian vault as durable memory and a
> separate agent-memory store. Spec: `VISION.md`.
>
> **Stack:** Python 3.12+, `uv` for env/deps. MCP via the official `mcp` SDK (FastMCP for
> servers). Stores on SQLite (`sqlite-vec` + FTS5). `pytest` / `ruff` / `pyright`.
> **Build/check:** `make check` (ruff + pyright + pytest).
>
> **Two layers, built in order:**
> 1. **The bot** (`VISION.md`) — built by hand, capability by capability.
> 2. **The self-improving loop** (`siloop.md`, `sandbox.md`, `VERIFIER.md`, `REVIEW.md`) —
>    built by hand *after* the bot, then used to auto-build new capabilities for the bot.
>
> Autonomy is the last thing that turns on, never the first. Build the bot manually, build
> the loop manually, *then* let the loop build. The governing docs above are **protected**:
> the builder reads them but never edits them (siloop invariant 7).

---

## Coding guidelines

1. **Think before coding.** State assumptions, surface tradeoffs. Unclear → ask before
   implementing. Multiple interpretations → present them, don't pick silently. Plan before
   every major change.
2. **Simplicity first.** Minimum code that solves the problem. No speculative abstractions,
   no unrequested config knobs, no error handling for impossible cases. If 200 lines could
   be 50, rewrite.
3. **Surgical changes.** Touch only what you must. No drive-by refactors, no reformatting
   untouched code. Remove orphans your change created; leave pre-existing dead code alone
   (mention it, don't delete it). Every changed line traces to the stated goal.
4. **Goal-driven execution.** Turn tasks into verifiable goals ("write the test, then make
   it pass"). State a brief plan for multi-step work; check off as you go.
5. **Explain before coding.** Say what you're building, why, and how it works conceptually.
   Then code.
6. **Concise code docs.** Comments and docstrings are short one-liners; detailed explanation
   goes in chat, not source. After each change, update this file so it matches the codebase.

---

## Working agreements

_Set at the start of the Foundation milestone, on 2026-06-13. Valid until revised._

- **Plan before building.** When you ask me to build something, I first scope it in `PLAN.md`
  (current task + ordered steps), adding a `design/<feature>.md` if it's a large feature —
  surfacing assumptions and any two-sided calls — *then* code. Small slices: `PLAN.md` only. You
  see the plan before code lands.
- **One feature, one commit.** Each capability (per `VISION.md` §10 build order) lands on its
  own commit before the next starts. No "milestone everything" mega commit. Better smaller than
  larger; name each commit with `feat`/`fix`/the appropriate prefix and keep the message concise.
- **Push after each commit.** This repo has a remote (`origin`); push `main` right after
  committing so it stays current — no batching. (The Obsidian vault's git is local-only and is
  never pushed — `VISION.md` §6.)
- **Verify before every commit.** Run the verifier's **fast profile** (`VERIFIER.md` checks
  1–5: build → typecheck → lint → existing tests → secret scan) — the same deterministic gate the
  auto-builder runs at full depth, just shallower. This is what keeps `main` green, which the
  auto-builder's "existing tests pass" check relies on. Then a self-review pass against the
  judgment dimensions in `REVIEW.md` (conformance / scope / edge cases / logic / design /
  security / tests). Blockers fix before commit; minors → `BACKLOG.md`.
- **Autonomy inside a milestone.** Make the call on design details as they come up. Log
  anything non-obvious:
  - architectural or surprising choice → append `DECISIONS.md`
  - "user should see this" at milestone end → append `BACKLOG.md`
  - stuck, or a genuinely two-sided call → **ask**.
- **Deferred scope goes to BACKLOG, not code comments.** A `TODO` without a matching
  `BACKLOG.md` entry is a review blocker (`REVIEW.md` §7).

---

## File map

Only this file loads automatically. Read the others on their trigger — never load the whole
set "just in case." Two families, on different axes:

### Process docs — the working state, churns as you go

| File | Read it when… | Write it when… |
|---|---|---|
| `HANDOFF.md` | first thing, every session | session end — overwrite with current state |
| `PLAN.md` | session start, right after HANDOFF | scope changes, a task completes, session end |
| `ARCHITECTURE.md` | starting a feature; need the system map | a component, boundary, or data flow actually changes |
| `DESIGN.md` | finding a feature's design doc (it's the index) | a feature's design is added/built — update its blurb + link |
| `design/<feature>.md` | before building that feature | while designing/building it; revise to as-built |
| `DECISIONS.md` | a past tradeoff is relevant to current work | an architectural/surprising choice is made — append |
| `BACKLOG.md` | planning what to do next | deferred scope, review minors, end-of-milestone notes — append |

The "before every commit" checklist role is filled by the verifier's **fast** profile —
see `VERIFIER.md`, not a separate REVIEW checklist.

### Spec & build-plan docs — read on trigger; **protected** (read, never edit)

| File | Owns | Lifespan |
|---|---|---|
| `VISION.md` | the bot's north-star: principles, intended design, build order | durable |
| `VERIFIER.md` | the gate pipeline (what every change is checked against) | durable — runtime obligation |
| `REVIEW.md` | the advisory AI-review rubric (loaded into the review subagent) | durable — runtime obligation |
| `siloop.md` | the loop's **build plan** + its invariants/contracts (the constitution) | **transient build plan** → see below |
| `sandbox.md` | the sandbox threat-model reminder + build plan | **transient build plan** → see below |

**Transient build plans.** `siloop.md` and `sandbox.md` are scaffolding. Once each is built,
its as-built design moves to `design/<feature>.md` and the build-plan doc is deleted. **Catch:**
`siloop.md` also owns the loop's invariants/contracts, which are load-bearing at *runtime* — so
when it's deleted, those invariants must survive into `design/self-improving-loop.md`, and
`VERIFIER.md`'s protected-path list repoints to the new design filenames. Don't let the
constitution evaporate with the build plan. (Rule of thumb: docs describing *runtime
obligations* stay; docs describing *how to construct something* get superseded by a `design/`
doc, then deleted.)

### What each file owns (so they don't blur)

- **VISION.md** — the *intended* design. The destination; stays full.
- **ARCHITECTURE.md** — the *as-built* system map; diverges from VISION as code lands. Early on,
  near-empty and points at VISION.
- **DESIGN.md** — the *index* of feature designs: one blurb + status + link per feature. Holds
  **no design content itself** (that lives in `design/<feature>.md`).
- **design/`<feature>`.md** — how one feature works internally. Kebab-cased after the feature.
- **PLAN.md** — the work queue: scope, current task, next. Empties as work finishes.
- **DECISIONS.md** — append-only log of *why* a non-obvious choice was made.
- **BACKLOG.md** — append-only list of deferred work and review minors.
- **HANDOFF.md** — the save-state: enough context to resume cold next session.

---

## Session flow

```
start  →  read HANDOFF.md  →  read PLAN.md  →  work the queue
work   →  (per feature) design/<feature>.md → ARCHITECTURE if map changes → build → VERIFIER fast → commit
end    →  update PLAN.md  →  overwrite HANDOFF.md
```
