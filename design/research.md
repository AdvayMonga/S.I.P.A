# design/research.md

The **research flow** (VISION §5.10) — turn transient web results into a durable, sourced,
`[[wikilinked]]` vault note. The point isn't a new information source (that's the `web` server); it's
a *workflow* that grows the linked corpus retrieval later bites on.

## Why it's a flow, not a server or tool

SIPA servers are leaf capabilities — **they never call each other** (shared logic goes into a
library like `vaultfs`, not server→server calls). Research spans servers: `web_search`/`web_fetch`
(web) → synthesize → `vault_create_note`/`vault_resolve_link` (obsidian). Only the **agent loop**
(the core's routing job) can call across servers. So research is *forced* to be a flow the agent
runs, not a `research` server.

**v1 builds no new tool.** It's a SYSTEM playbook over tools that already exist + the existing
iterative agent loop (`loop.py:_run_loop` already loops tool-call → result → repeat). Schema lives in
the prompt; the model writes via `vault_create_note`. A schema-enforcing tool is deferred hardening,
added only if formatting drifts.

## Two depths (the model classifies on criteria, not a numeric threshold)

- **Shallow** — single fact / quick lookup: answer inline, ≤1 `web_search`, **no note**.
- **Deep** — multi-source / multi-entity / comparison / worth keeping: run the flow, save a note.
- **Explicit overrides win** ("deep research…" / "save this" → deep; "just quickly check" → shallow).
- **Borderline** → answer inline, then offer to save.
- **Vague topic** (scope/region/budget/use-case unclear) → ask **one** clarifying question first.

## The flow (mirrors how OpenAI/Gemini/Perplexity/Anthropic structure deep research)

1. **Decompose** — break the request into sub-questions along its dominant axis (per entity /
   attribute / theme); search each separately, never one broad query.
2. **Iterate** (uses the existing loop, not a new one) — read results, `web_fetch` the full page for
   anything stated as a finding (snippets are lossy), spot gaps, search again, until each
   sub-question is covered.
3. **Ground** — every finding cites a source actually fetched, inline `[^n]`; drop or flag anything
   ungroundable. This is the anti-hallucination mechanism. *(Code-side enforcement — validate
   footnote URLs ⊆ fetched URLs — belongs in the core, deferred to `BACKLOG.md`.)*
4. **Adversarially verify** (`verify_claims` tool, `src/bot/verify.py`) — before saving, the model
   passes its key factual claims to `verify_claims`, which fans out **independent skeptic
   sub-agents** (reusing `run_subagents`) that each try to *refute* the claim via web search. Each
   sees **only the claim, never the reasoning** that produced it — that independence is the whole
   point (a model checking its own findings rubber-stamps them). `VOTERS=2` per claim; aggregation
   is **skeptical**: `refuted` if any skeptic refutes, `supported` only if all confirm, else
   `uncertain`. The model drops `refuted`, marks `uncertain` as unverified, keeps `supported`.
   Offered only on top-level turns (alongside `delegate`), so a skeptic — which runs with
   `allow_delegate=False` — can't recurse into more verification. Cost scales with claims × voters;
   `VOTERS` is the dial.

## Note schema — fixed envelope, adaptive body

`Research/<topic>.md`:
```markdown
---
created: <date>
type: research
topic: <topic>
---
## Summary        # 2-4 sentence skim layer (constant)
<synthesis>
## <dominant axis section>   # body mirrors the question: ## per entity / sub-question / theme
- <finding> [^1]
## Sources        # constant footer — footnoted, only fetched URLs
[^1]: <title> — <url>
## Related        # constant footer — [[wikilinks]] resolved via vault_resolve_link
[[Existing Project]] · [[Some Person]]
```
**Header + footer are fixed; the body is free-form, organized by the dominant axis** ("X, Y, Z about
A, B, C" → section per company). Default **one note** sectioned by entity; the model splits into
linked per-entity notes only when asked or when entities are clearly distinct subjects. An existing
note on the topic is **updated, not duplicated**.

## Where it lives

The playbook is a `# Research` section in `loop.py`'s `SYSTEM` constant (stable behavior; small,
present every turn so the model can make the shallow/deep call). No code logic, no new tests — it's
instruction. Runs in whatever thread invoked it; the concurrent-chat pool already gives
background/swap/stop for free (no delegation in v1).

## Deferred (see `BACKLOG.md`)

- ~~**Adversarial claim-verification**~~ — DONE (`verify_claims`, step 4 above).
- **Code-side citation validation** in the core (footnote URLs ⊆ fetched-this-turn URLs) — the
  stronger grounding mechanism; first hardening if a hallucinated cite ever appears.
- **Schema-enforcing `vault_write_research_note` tool** — only if the model's formatting drifts.
- **Multi-agent fan-out per entity** — for large multi-entity research, spawn a sub-agent per entity
  in parallel (reuses the existing `delegate` machinery), then synthesize.
