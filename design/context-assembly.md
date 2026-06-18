# design/context-assembly.md

Context assembly v2 — the thing that makes S.I.P.A. *feel* like it knows you. Realizes
`VISION.md` §5.9. Today retrieval is **agentic** (the model must choose to call `memory_recall` /
`semantic_search`); after this, the relevant slice is **auto-injected into every turn**, so a fresh
session has continuity from memory and answers grounded in notes — without the user invoking a tool.

This is the "layer 2 → layer 1 glue" from the 3-layer memory model: pull the relevant part of the
durable stores into working memory automatically, every turn.

## What it does (per turn, once)

Before the model call, build **one token-capped context block** from three sources, each tagged
with provenance so the model can cite/link, then prepend it to the system prompt:

1. **Profile** — `memory_get_profile()`, injected **always** (the small always-on core).
2. **Agent memory** — `memory_recall(query=user_message, k)` → top-k distilled facts/episodes.
3. **Vault notes** — `semantic_search(query=user_message, k)` → top-k note chunks by meaning.

"Never dump a whole store" (§5.9): each source is capped; the whole block is capped. Graph
expansion (one hop) is **deferred** (`BACKLOG.md` — `expand_context`).

## Where it lives

New module **`src/bot/context.py`**: `assemble_context(host, user_message, base_system) -> str`.
The loop (`run_turn`) calls it **once** at the start of a turn and reuses the result across the
turn's tool-use iterations (retrieval keys off the user message, not the intermediate tool steps).

Stays pure-MCP: `context.py` calls `host.call_tool(...)` — core never imports a server. The three
servers it pulls from (memory, vault_search) are already spawned by the host.

## Format (provenance-first)

```
<base SYSTEM prompt>

# Context (auto-retrieved; use if relevant, ignore if not; cite the source you use)

## About the user
[preference] likes terse replies
[house_style] kebab-case note names

## Possibly relevant memory
- (memory#12 · fact) flight to NYC is June 20
- (memory#7 · episode) on 2026-06-13 we built the memory server

## Possibly relevant notes
- (vault: Projects/Summer.md › Goals) ship the daemon, then context assembly …
```

Provenance tokens: `memory#<id>` for recall entries, `vault: <path> › <heading>` for note chunks.
A one-line preamble tells the model these are *candidates* (may be irrelevant) and to cite the
path / `[[wikilink]]` it actually uses. The search tools stay available — auto-injection covers the
ambient case; the model still calls tools for deep dives.

## Query transformation (the retrieval query, not the literal message)

Built later (BACKLOG §51b). Retrieval keys off a **rewritten** query, not the user's literal words.
`src/bot/query.py:rewrite_query(provider, convo, msg)` resolves a context-dependent follow-up
("what about the second one?") into a standalone, keyword-rich query using the rolling summary +
last few turns — so the pronoun's *referent* is what gets embedded, not the vague surface form.

Gated (`_needs_rewrite`): the model call fires **only** when there's prior history AND the message
looks dependent (a pronoun/deixis marker, or ≤6 words). Standalone questions and turn-1 skip it —
no added latency or cost. The rewrite is **retrieval-only**: never shown, never appended to
`messages`, so a bad rewrite degrades recall slightly but never corrupts the conversation. On
provider error or an empty rewrite it degrades to the raw message. The loop skips it entirely on
trivial turns (they don't retrieve). This replaced the earlier blunt `summary[-500:] + msg` concat,
which was empty before the first compaction (the common 2–3-turn case) and diluted rather than
resolved.

## Token budget (one cap, allocated across sources)

VISION says "token-capped". For M6, budget in **characters** (~4 chars/token heuristic) — a real
tokenizer (`provider.count_tokens`) is the later upgrade (`BACKLOG.md`). One total cap, allocated:

- **Profile** first — it's already capped at 2000 chars by the memory store; it always gets its slot.
- **Remainder** split between memory and vault; within each, take entries in rank order until the
  per-source slice is full, then stop (truncate the last snippet). Empty sources are omitted.

Constants live in `context.py` (no config-knob sprawl per CLAUDE.md): `TOTAL_BUDGET`,
`K_MEMORY`, `K_VAULT`, per-source slices.

## Graceful degradation

Each retrieval is wrapped: if a server errors or returns nothing, that **section is skipped**, never
crashing the turn. If all three are empty (fresh install, empty stores), `assemble_context` returns
the base SYSTEM unchanged — behavior identical to today.

## Caching note (not done now)

A dynamic per-turn system prompt defeats Anthropic prompt caching on that block. Base SYSTEM is
small so the cost is minor; splitting static (cacheable) from dynamic (retrieved) context is a later
optimization (`BACKLOG.md`).

## Scope boundary — what M6 is NOT

- **Not the daemon.** This works in the current REPL; continuity-while-running and proactive
  triggers are the daemon's job (later in §10).
- **No rolling conversation summary / compaction.** Long-conversation compaction (layer 2 *within* a
  session) and session-summary-on-close (resume after restart) are separate — they distill the
  *transcript*; this assembles the *stores*. (`BACKLOG.md`.)
- **No graph hop, no real tokenizer.** Both deferred above.

## Done when

A **fresh** REPL session, with a fact in memory and a note in the vault, answers a question grounded
in both **and cites them**, without the user calling any tool. `make check` passes with unit tests
for `assemble_context`: profile always present, sections formatted with provenance, budget truncates,
empty stores → base SYSTEM, a failing retrieval degrades to skip.
