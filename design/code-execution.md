# design/code-execution.md

Interactive code execution (option A) — the big capability jump, built with the safety layers that
keep VISION's "autonomy is the last thing that turns on" intact. The autonomous/sandboxed version
(for the autobuilder) is a separate, later thing; this is the supervised, on-your-real-machine path.

## The safety layers

1. **Off by default.** The `exec` server spawns only when `EXEC_ROOT` is set. No root → no shell.
2. **Scoping.** `run_shell(command)` runs with `cwd = EXEC_ROOT`, a 30s timeout, and capped output.
3. **Approval gate.** `run_shell` is in `loop.APPROVAL_REQUIRED`. Before it runs, the loop's
   `Approver` asks the user `[y]es · [a]lways · [N]o`. **"always"** allowlists that exact command for
   the session (no re-prompt). `approval_mode="trust"` runs without asking at all. Reversible tools
   (vault writes auto-commit to git, reads, search) are **not** gated — they run freely. This is the
   Claude-Code permission model (free for safe, prompt for risky, allowlist/mode to cut prompts).
4. **Unattended-block.** `ask is None` on timer/background turns → `_approved` returns False → shell
   is **denied** when no human is watching. No autonomous shell without a sandbox.

## Approval round-trip (the reusable primitive)

A turn can ask the user mid-flight and wait. `Ask` is threaded source → `submit` → `Event.ask` →
router → `Handler` → `run_turn(ask=)` → `_approved`.

- **Terminal** (`StdinSource`): `ask` prints `sipa? …` and reads the answer on `approve>`. Works
  because the source's main loop is blocked awaiting the turn, so only `ask` is reading stdin.
- **Socket** (`SocketSource`): `ask` writes the question prefixed with `ASK_PREFIX` (`\x01?`) so the
  client knows it's a question (not a reply); the client's next line is the answer.
- **Unattended** (timer, background): no `ask` → `Event.ask is None` → gate denies.

This primitive is reused by anything that needs to ask the user (reminders, clarifications), not just
code execution.

## Why shell asks but file edits don't

Vault/file edits go through git (auto-committed) → reversible → no prompt; "undo" reverts. Shell is
**not** auto-reversible (`curl | sh` can't be git-undone) and a command's risk is hard to classify, so
shell asks. That's the risk-tiered model: reversible = free, irreversible/external = ask.

## Built since

- **`undo`** — `vault_undo` reverts the last S.I.P.A. vault commit (leaves your own edits alone).
- **Action summaries** — the system prompt has the bot report each action in one line.
- **Trust mode + "always" allowlist** — `Approver`, `approval_mode`.
- **Desktop approval card** — the Tauri `ask` command handles `ASK_PREFIX` questions: emits
  `approval-request` → the UI shows an Approve/Always/Deny card → the `approve` command sends the
  answer back over the socket. (Compile-verified; the GUI round-trip wants a live run to confirm.)

## Deferred (BACKLOG)

- **Sandbox** — isolated runtime so the autobuilder can run shell *unattended* safely.
