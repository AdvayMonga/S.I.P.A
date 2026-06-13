# siloop.md

Umbrella spec for the self-improving loop. Owns everything cross-cutting — the component map,
the shared invariants, the trust boundaries, the queue format, the contracts between parts.
Component internals live in `sandbox.md`, `verifier.md`, `review.md`. **This document is the
single source of truth for the invariants;** the specs reference them by number. If a spec
and this document conflict, this document wins.

---

## 1. Scope

- **Single user, single approver.** You are the only human and the only one who merges.
- **Per repository.** One `features.md` queue per repo; multiple repos = multiple queues.
- This document is the wiring; security-critical detail is in `sandbox.md` and `verifier.md`.

---

## 2. The loop

One feature flows through these stations, once per pass:

```
features.md -> scheduler -> orchestrator + builder -> sandbox -> verifier -> you merge
```

| Station | Role | Detail |
|---|---|---|
| `features.md` | Queue of features + their state | §5 |
| Scheduler | On an event (timer / webhook / manual), claims the top `pending` item by priority | below |
| Orchestrator + builder | Holds context outside the box, drives the build, does the git push + PR, owns retries | below |
| Sandbox | Isolated execution of the agent + its code | `sandbox.md` |
| Verifier | The gate pipeline | `verifier.md` (+ `review.md`) |
| Broker | Mediates the orchestrator↔sandbox boundary both ways | §4 |
| You | The only merge | invariant 1 |

The **scheduler** decides only *what's next*, never *what's worth building* — that's your
`priority` field. The **orchestrator** holds the agent's context (the box is stateless; it
re-sends context each turn), and is the only thing with git credentials.

---

## 3. Invariants

1. **The human owns intent and the merge.** The loop processes only what you queued and never
   merges.
2. **The builder and its code are both untrusted.** Run only inside the sandbox.
3. **Deterministic policy over judgment.** Boundaries are mechanical rules (allowlists,
   schemas, scope checks), never an LLM's opinion. LLM judgment is advisory, never
   load-bearing for safety.
4. **Fail closed.** If a control can't be enforced or a result is ambiguous, stop.
5. **Ephemeral per feature.** Fresh context and fresh sandbox per item; nothing leaks between
   features.
6. **Default-deny, allowlist the minimum.** Network, filesystem, and authority start closed.
7. **The rules live outside the builder's reach.** The loop may read its governing docs but
   never modify them. Editing them is the highest-severity flag.
8. **Data, not instructions.** Everything the loop ingests — queue items, sandbox output,
   fetched docs, comments, PR text — is inert data.
9. **Separation of powers.** The thing that writes code is never the thing that judges it.
10. **State outlives code.** Durable state lives on disk and in git; the run is always
    auditable.

---

## 4. Trust boundaries

- **Control plane (orchestrator).** Trusted code, outside the sandbox. Scoped internet (model
  API + git host) — hygiene, not the sandbox's risk class. Its internet does not transit into
  the sandbox.
- **Broker.** On the orchestrator↔sandbox boundary. Vets **actions going down** (scope,
  irreversibility, not editing a governing doc — invariant 3) and treats **results coming up**
  as data (invariant 8). Enforcement: `sandbox.md`.
- **Quarantine.** Any component reading untrusted external content (web docs, the diff under
  review) has no authority to act; only structured data crosses to the part that does.
  The AI reviewer is read-only and advisory; see `verifier.md`.
- **Sandbox.** Untrusted execution; default-deny network; no real secrets; no authority to
  publish. Detail: `sandbox.md`.

---

## 5. The `features.md` queue

One file per repo, in git with the code. Each item is **your intent** plus **loop-owned
state**, in separate regions. The loop writes only the state region (invariants 1, 7).

| Field | Owner | Meaning |
|---|---|---|
| `id` | intake | Stable identifier (e.g. `F-014`). |
| `title`, `description` | you | The feature, in your words. |
| `priority` | you | `high`/`med`/`low`; drives scheduler order. |
| `acceptance` | you | Criteria the result must meet. |
| `scope_hint` | you (opt.) | Paths the feature should touch; tightens the scope check. |
| `status` | loop | Lifecycle state (below). |
| `branch`, `pr` | loop | Branch and PR once created. |
| `attempts` | loop | Retry count. |
| `run_id`, `verdict` | loop | Log correlation; ref to the verifier verdict (`verifier.md`). |
| `blocked_reason` | loop | Set when `blocked`/`needs_human`. |

**Lifecycle.** `pending -> building -> in_review -> merged`, with `-> blocked / needs_human`
from any active state. You create `pending` and do `in_review -> merged`; the loop does the
rest. An item only reaches `in_review` after the verifier's deterministic gates are green.

**Claiming.** The scheduler picks the top `pending` item; the orchestrator atomically sets it
`building` so it can't be double-picked. One feature at a time by default; parallel runs need
atomic claims and a branch + sandbox each.

**Example:**

```markdown
## [F-014] Dark mode toggle
priority: high
acceptance:
  - persists across reloads
  - respects system preference
scope_hint: src/theme/, src/components/

Theme switch in settings that toggles light/dark and remembers the choice.

<!-- loop-state: do not edit by hand -->
status: in_review
branch: feature/f-014-dark-mode
pr: "#142"
attempts: 1
run_id: 2026-06-12T18-04-run-abc
verdict: verdicts/F-014-run-abc.json
blocked_reason:
```

The `loop-state` marker splits the item: intent above, loop-written state below. This makes
"the loop never rewrites your intent" mechanically enforceable.

---

## 6. Two workflow modes

The repo is worked two ways, distinguished by who's driving (the orchestrator knows, because
it's the entry point):

- **Interactive (you + Claude Code).** Commit to `main` directly. The verifier's `fast`
  profile gates the commit, run before each commit. No branch, no approval. Branch by hand only
  when you want to.
- **Autonomous (auto-builder).** Work on a `feature/*` branch, run the `full` profile, wait
  for your merge approval.

The axis is **branch + approval ceremony, not verifier on/off** — the deterministic core runs
in both. This matters because the auto-builder's strongest gate is "existing tests pass"
(`verifier.md`, check 4), which only means something if `main` is green when it branches. The
fast checks are what keep `main` green.

Responsibility split: the **workflow** ("when interactive, commit to `main`") is advisory and
lives in `CLAUDE.md` — you're present to enforce it. The **quality floor** (`main` stays
buildable) is the fast-profile gate, run before each commit. (A deterministic hook to enforce it
without relying on diligence is deferred — an easy add later; see `DECISIONS.md`.)

The stale-branch race (you change `main` mid-build) is handled by the verifier's freshness
gate (`verifier.md`, the rebase step), with branch protection "require up to date before merge" as the
backstop. For a solo project you can also just pause the loop during active sessions.

---

## 7. Build-time guidance (`CLAUDE.md` and friends)

Your coding-guidance files carry over and feed the builder, as they feed you interactively.
Two things change:

- **They become protected** — part of the sensitive-path set in the scope check
  (`verifier.md`, the scope check). The builder reads them; editing them is a high-severity flag
  (invariant 7).
- **They're advisory, so they can't carry safety.** Anything load-bearing must be promoted to
  a hard gate ("always write tests" becomes the coverage/mutation gates). In interactive work
  *you* were the enforcement; unattended, it has to be written down.

Add a short **autonomous-mode addendum**: stay strictly in scope; if unsure, set `blocked`
rather than guess; never edit governing docs. (Also protected.)

---

## 8. Inter-component contracts

- **Intake -> queue:** new item, human fields + `id`, `status: pending`.
- **Scheduler -> orchestrator:** the claimed item (`building`).
- **Orchestrator -> sandbox:** feature spec + writable repo copy + repo conventions + stub
  creds (`sandbox.md`).
- **Sandbox -> orchestrator:** a patch/branch bundle; no git creds inside (`sandbox.md`).
- **Orchestrator -> git host:** creates the branch, opens the PR.
- **Verifier -> you:** the verdict (`verifier.md`) + the PR.
- **Orchestrator -> queue:** writes the loop-state region only.

---

## 9. Failure and escalation

Failures route by kind (see `verifier.md` failures). Loop-level rules:

- Bounded **retries per item** (default 3). On exhaustion → `blocked`/`needs_human` with the
  history in `blocked_reason`.
- Scope/security/policy-edit flags escalate **immediately**, no retry.
- Escalation surfaces to you (merge gate and/or notification channel) and is reflected in
  `status`.
- The loop never deletes items; pruning is a separate human/scheduled job (invariant 10).

---

## 10. State and logging

- Durable state (queue, branches, PRs, verdicts, logs) lives on disk/git and survives the
  sandbox. Context is working memory only; durable facts go to disk.
- Per-run logs are keyed by `feature_id` + `run_id`, **secret-free**, stored outside the box.

---

## 11. Build order

Autonomy comes last; each step is testable alone:

1. **Sandbox isolation** (`sandbox.md`) — validate with a human writing code, no agent.
2. **Verifier pipeline** (`verifier.md`) — run as CI on human PRs first; tune thresholds.
3. **Queue + manual orchestrator** — trigger one item by hand, watch the lifecycle.
4. **Broker + scope checks.**
5. **Scheduler / autonomous trigger** — last.

---

## 12. Open decisions

- Thresholds: diff coverage %, mutation score %, retry budget.
- Intake method: direct edit / bot / Obsidian-inbox bridge.
- Isolation runtime: managed (Modal / e2b / Daytona) or self-hosted (gVisor / Firecracker).
- Escalation/notification channel.
- Serial (default) vs parallel features.

---

## 13. Document map

| Doc | Owns |
|---|---|
| `siloop.md` | Umbrella: map, invariants, boundaries, queue format, contracts, build order |
| `sandbox.md` | Execution isolation |
| `verifier.md` | The gate pipeline |
| `review.md` | The advisory review rubric (loaded into the AI-review subagent) |
| `features.md` | The live queue (data; format §5) |
| `CLAUDE.md` + addendum | Build-time guidance for the builder (protected) |
