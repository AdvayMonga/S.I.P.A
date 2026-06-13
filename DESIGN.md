# DESIGN.md

Index of feature designs. One blurb + status + link per feature. **No design content lives
here** — the full design for each feature is in `design/<feature>.md`. This file is the table of
contents; keep it that way.

Status: `planned` · `building` · `built`.

| Feature | Status | Design doc | Blurb |
|---|---|---|---|
| _none yet_ | — | — | First design doc gets added here when a feature is large enough to need one (M0 is small — `PLAN.md` covers it). |

---

### Conventions

- **When to add a row.** A feature earns a `design/<feature>.md` (and a row here) when it's
  bigger than a `PLAN.md` task can carry — e.g. semantic index, memory, the self-improving loop,
  the sandbox. Small slices live in `PLAN.md` only.
- **Naming.** `design/<feature>.md`, kebab-case after the feature
  (`design/self-improving-loop.md`, `design/sandbox.md`, `design/semantic-index.md`).
- **As-built.** Each design doc is revised to reflect what was actually built. The transient
  build plans (`siloop.md`, `sandbox.md`) are superseded by their `design/` docs and then deleted
  (carry their invariants/contracts across first — see `CLAUDE.md` file map).
