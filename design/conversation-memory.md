# design/conversation-memory.md

The conversation layer — the within-session "HANDOFF". M6 (`context-assembly.md`) assembles the
durable **stores**; this assembles the **transcript**. Together they are layers 1–2 of the 3-layer
memory model: working memory (the live messages) + compaction (fold old turns into a rolling
summary when the window grows).

Realizes the deferred "rolling summary + transcript compaction" (`BACKLOG.md`, approved 2026-06-14).

## What it does

A `Conversation` holds `messages` (the live turns) + `summary` (a rolling synopsis). Per turn:

1. **Compact if grown** — once the conversation passes a turn threshold, LLM-summarize the older
   turns into `summary` and drop them from `messages`, keeping the most recent turns verbatim. Bounds
   the context window so long sessions don't blow it (what Claude Code does internally).
2. **Enrich retrieval** — the retrieval query becomes `summary-tail + user_message`, so follow-ups
   ("and the next step?") retrieve against conversation state, not just the bare message.
3. **Inject the summary** — `# Conversation so far\n{summary}` is appended to the system prompt, so
   the context dropped by compaction survives in compressed form.

## Where it lives

- **`src/bot/conversation.py`** — `Conversation` dataclass + `maybe_compact(convo, provider)` +
  summarization. Pure of MCP; needs only the provider (an LLM call when compaction fires).
- **`src/bot/loop.py`** — `run_turn` takes a `Conversation` (was a raw list). It compacts, enriches
  the query, assembles context (M6), injects the summary, then runs the turn as before.
- **`src/bot/cli.py`** — holds one `Conversation` for the REPL; passes it to `run_turn` and the
  on-open scheduled tasks (they share the same conversation).

## Compaction algorithm (pairing-safe)

Anthropic requires every `tool_result` to follow its `tool_use`, so we never cut mid-pair. We cut
only at **real user turns** (role `user`, string content — not a `tool_result` list):

- `turns = indices of real user messages`
- if `len(turns) <= COMPACT_AFTER_TURNS` → no-op
- `cut = turns[-KEEP_RECENT_TURNS]` → summarize `messages[:cut]`, keep `messages[cut:]` (a clean
  window that starts at a user message, all pairs intact)
- `summary = LLM(prior summary + dropped transcript)`

Constants in `conversation.py`: `COMPACT_AFTER_TURNS = 12`, `KEEP_RECENT_TURNS = 4`. The summarizer
is a tool-less `provider.generate` call with a compress-this-conversation system prompt that merges
the prior summary (facts, decisions, open threads, preferences; drop chit-chat).

## Scope boundary

- **Session-summary-on-close / resume-after-restart is NOT here.** That persists the summary across
  process restarts and belongs with the daemon (it needs a real session lifecycle; the REPL's
  boundaries are fuzzy). M7's summary lives in memory for the session. Persisting it (and optionally
  distilling it into the memory store as an `episode`) is the daemon's job — `BACKLOG.md`.
- **Char-count thresholds, not a real tokenizer** — same heuristic stance as M6.

## Done when

A long REPL conversation (past the threshold) compacts: old turns fold into the summary, recent turns
stay verbatim, the summary is injected and used to enrich retrieval — and the turn still completes
normally with tool pairs intact. `make check` green with unit tests for `maybe_compact` (no-op under
threshold; folds + trims over it; cut lands on a clean user turn) and the transcript renderer.
