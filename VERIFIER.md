# VERIFIER.md

The verifier is a set of checks that run on a code change before it can merge. It judges the
change, not who wrote it — so the same checks apply whether the auto-builder made the change or
you did, just with different ceremony around them (the two flows below).

Two rules sit under everything:

- The automated checks either pass or they don't. They block on failure and can't be argued
  with. The AI review is advisory — it can flag things, but it never blocks and never merges.
- Only you merge. The verifier's job is to decide whether a change is worth your time, not to
  approve it for you.

## The checks, in order

Run top to bottom; stop at the first hard failure. Tools named are examples — match them to the
repo. Thresholds are tunable.

1. **Build** — compiles from a clean checkout.
2. **Typecheck** — no new type errors.
3. **Lint / format** — no new style violations.
4. **Existing tests** — the tests already in the repo still pass. Proves the change didn't break
   what worked. The builder can't weaken this; these tests predate it.
5. **Secret scan** — no credentials, API keys, or `.env` contents in the diff (gitleaks /
   trufflehog). Cheap and runs in both profiles. A hit escalates immediately — rotate the
   leaked secret; never just a retry.
6. **New-code coverage** — the changed lines are covered by tests (e.g. 80% of the diff).
7. **Mutation testing** — flip operators and conditions in the new code and confirm the tests
   fail. If they don't, the tests assert nothing. This is what makes the builder's own tests
   trustworthy — without it, "tests pass" means nothing, since the builder wrote them.
8. **Scope check** — the change only touches files it should. Hard-flag anything touching
   sensitive areas: auth, payments, CI config, dependencies, secrets, and the governing docs
   themselves (`siloop.md`, `sandbox.md`, `verifier.md`, `review.md`). An agent editing the
   rules that judge it is the worst-case flag.
9. **Security** — run SAST (semgrep/bandit) and audit any new dependencies.
10. **AI review (advisory)** — an LLM reads the change against `review.md` for what tools can't
   catch: does it actually do what was asked, missed edge cases, bad design, subtle bugs. It
   only runs on changes that are big or risky (e.g. 300+ lines, or touching sensitive paths, or
   adding dependencies) — small low-risk changes skip it. It returns its verdict through a tool
   call so the output is always well-formed, and that output is checked before it's used. It can
   request changes or leave comments; it never blocks or merges.

## Two profiles

Same checks, two depths:

- **fast** — checks 1–5 (build → typecheck → lint → existing tests → secret scan; optionally 8,
  scope), run before each commit. Quick. No mutation testing, no AI review.
- **full** — all checks, run on the auto-builder's branch.

## Flow: auto-builder

1. The builder finishes the feature on a new branch.
2. Run the full checks. Any automated check (1–9) fails → send it back to the builder to fix,
   count one attempt. The branch doesn't reach you until 1–9 pass.
3. If the AI review requests changes, send it back once more (within the retry budget), then
   surface to you with the notes.
4. Before showing you the branch, rebase it onto current `main` (which may have moved if you
   committed in the meantime) and re-run the automated checks on the result. If the rebase
   conflicts, stop and hand it to you — don't auto-resolve.
5. The branch and its results come to you. You merge or you don't.
6. If the retry budget runs out (default 3), mark the item `blocked` and hand it to you with the
   history.

## Flow: interactive (you + Claude Code)

1. You work directly on `main`.
2. The fast checks run before each commit. If they fail, fix before committing — this keeps
   `main` green, which the auto-builder relies on (its check 4 branches off `main`).
3. No branch, no review, no approval. Branch by hand only when you want to.

## What happens on a failure

- An automated check fails → back to the builder, counts as an attempt.
- The AI review requests changes → back once, then surface to you.
- The AI review leaves only minor comments (nits) → attached to the PR, no rebuild.
- Retry budget exhausted → `blocked`, escalate to you.
- Anything touching sensitive paths or a security issue → escalate to you immediately, no retry.

## The reviewer is swappable

The AI review's instructions live in `review.md` today; later it could be a skill. Either way
the contract is fixed: it gets only the change, the spec, and the check results — a fresh,
read-only context each time — and returns its verdict through the same tool call. A skill must
stay read-only and advisory, and counts as a protected file.
