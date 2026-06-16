# design/sub-agents.md

Sub-agents — the bot delegates work to **isolated agent loops** (own context, same tools) and uses
their results. Realizes VISION §10 "Sub-agents". Two modes; we build the first now.

## The primitive

A sub-agent = `run_turn` on a **fresh `Conversation`** against the same `host` (so it has the tools),
returning its final text. Isolation is the point: the sub-agent's back-and-forth never touches the
main conversation — only its conclusion comes back.

`subagent.run_subagents(tasks, provider, host)` runs each task as a sub-agent, **concurrently up to
`MAX_SUBAGENTS` (5)** (an `asyncio.Semaphore`), and returns the list of results in order.

**Recursion is capped at one level:** the `delegate` tool is offered *only* at the top level
(`run_turn(..., allow_delegate=True)`). Sub-agents run with `allow_delegate=False`, so they have no
`delegate` tool and can't spawn their own — no fan-out explosions.

## Mode 1 — fan-out (built now)

The model calls **`delegate(tasks=[...])`** with independent sub-task prompts. The loop runs them in
parallel (capped), then hands the model back all results to synthesize. For *one big task that splits
into independent parts* — research several topics, review many files. The main turn waits, but the
parts run concurrently so it's faster, and each sub-agent's context stays tight.

The tool description tells the model: use it only for genuinely independent work; do small or
sequential things itself.

## Mode 2 — background delegation (next, deferred)

"Kick off the research, hand me back control, ping me when it's done." The sub-agent runs as a
**detached background task**; the main loop returns immediately; on completion the result is posted to
the **event router** as an event — exactly like the wall-clock timer firing (M8). The architecture
already has the shape for this (the router is a multi-source async dispatcher); we add a background
spawn + a completion event source. Needs a *shared* concurrency cap (the sync mode's per-call
semaphore suffices only because the daemon runs one turn at a time today). See `BACKLOG.md`.

## Costs & caveats

- Each sub-agent is a full agent loop (several model calls) — fan-out is ~N× the tokens. The cap (5)
  bounds it; M12's cost log shows it.
- Results come back as **summaries** (each sub-agent's final text), not raw transcripts — that's the
  context-isolation benefit, but you get conclusions, not the working.
- Decomposition is the **model's** job (what to split, how many); the harness just provides spawn +
  cap. Works best on independent chunks; dependent work doesn't parallelize.

## Toward the autobuilder

Sub-agents are foundational to `siloop`: the autonomous builder fans out builders / verifiers /
reviewers as sub-agents. Building this interactively now is groundwork for that (run autonomously in
the sandbox later).
