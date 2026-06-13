# sandbox.md

The sandbox is the locked box the auto-builder runs in. Both the agent and the code it writes
are untrusted, so they only ever run here — never on the host. A bad run can't reach your
machine, your secrets, the open network, or `main`.

> **Status: threat-model reminder, not a contract.** This doc lists what can go wrong with an
> untrusted builder so no category is forgotten — not a fixed set of controls to implement up
> front. The runtime is deferred and swappable behind the broker (`siloop.md` §4); start simple
> and harden as you learn. See `DECISIONS.md` (2026-06-13).

## Rules

- **Isolation** — use a kernel-isolated sandbox: gVisor or a microVM (Firecracker), or a managed
  option (Modal, e2b, Daytona) that gives you this. Plain Docker isn't enough — it shares the
  host kernel. Run as a non-root user.
- **Fresh box per feature** — one box per feature, destroyed after. Nothing carries over.
- **No real secrets** — the box gets stub/fake credentials only, never production keys or your
  `.env`. Never put secrets in the agent's context or logs (they end up in transcripts).
- **Default-deny network** — block everything, then allow only what's needed: the model API
  (the agent's brain), package registries (npm, pypi, etc.), and OS mirrors. Everything else is
  blocked, so the agent can't exfiltrate. During tests, lock it down further — offline by
  default, mock any external service.
- **Repo copy only** — mount a writable copy of the repo plus one output folder. Nothing else:
  no host folders, no Docker socket, no orchestrator files.
- **No publishing** — the box holds no git credentials and can't push, merge, change settings,
  or edit the governing docs. It writes its work as a patch; the orchestrator, outside the box,
  creates the branch and PR.
- **Limits** — set CPU, memory, disk, and time limits before it runs. If it tries to break out
  (reach a blocked host, write outside its folders, touch the host kernel), abort and flag it —
  never silently retry.

## Flow

1. Provision a fresh isolated box with the limits set.
2. Seed it: a copy of the repo, the feature spec, the repo's coding guidelines, stub credentials.
3. **Build** — the agent implements the feature. Network = the build allowlist.
4. **Test** — the verifier runs its checks. Network = offline / mocked.
5. **Emit** — write the result as a patch to the output folder. The box never pushes.
6. **Destroy** the box. Only the patch and the run logs survive.
