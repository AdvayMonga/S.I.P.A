# design/dashboard.md

The desktop is a **customizable instrument dashboard**: every capability is a **module** (tile) on a
grid, showing that capability's current/upcoming state. Full-screen. The operator-console identity,
realized. Evolves the earlier `PanelGrid`.

## Decisions (2026-06-16)

- **Placement:** drag-and-drop, **snap to grid**. An edit mode toggles dragging on; otherwise locked.
- **Modules are built individually** per capability — each is its own component, not one generic
  thing. Default stance: **mini control panels** (interactive where it makes sense — cancel an agent,
  expand a result), but spec'd case-by-case. Chat is the biggest module and the main thing.
- **Layout:** no named/multiple layouts. **One default layout that persists across sessions**
  (localStorage). Change it once, it stays.
- **Footprints:** a small set of fixed sizes (1×1, 2×1, 2×2, …) each module picks from; chat largest.
- **Staging:** build the **backbone first** (grid + customization + persistence + module registry),
  wire modules incrementally as each capability's data exists. Don't ship all modules at once.

## Architecture

- **Module registry** (`modules/`): each module = `{ id, title, w, h (footprint), Component }`.
- **Grid** (`Dashboard`): `react-grid-layout` — snap-to-grid, **fixed size** (`isResizable=false`),
  drag **by the tile's title-bar handle** in edit mode (so chat stays interactive). Add/remove modules
  via a menu of registry items not currently placed.
- **Persistence:** the layout (positions) + enabled module ids → `localStorage`, restored on load,
  merged against the registry (new code-defined modules appear as available to add).
- **StatusBar** keeps the state-pulse + session cost, plus an **edit-layout toggle**.

## The telemetry backbone (the real per-module work)

A module is only as good as the live state it shows, and the daemon currently *processes* turns more
than it *exposes* state. The pipe already exists — the M16 push/`:subscribe` channel. So: the daemon
broadcasts state snapshots (cost, running/queued background agents, upcoming scheduled fires, recent
memory), and each module subscribes to its slice. This is most of the effort; each module is then a
small view/control on top. Built per-capability as they're instrumented.

### Transport: one typed channel, not a separate one (2026-06-17)

Telemetry rides the **same** push/`:subscribe` channel as chat — not a second socket. The reason is
that the long-term cost lives in the **envelope schema, not the socket count**: get the envelope
typed and you can split transports later trivially; a second transport now just doubles the
reconnect/liveness/ordering surface for isolation we don't need (telemetry here is low-frequency, so
it can't starve chat on the shared serialized stream). See `DECISIONS.md` (2026-06-17).

**Envelope.** Every push payload is `{type, topic?, ...payload}`:
- `type: "chat"` — a narrative message to append to the conversation view (today's `sipa-push`).
- `type: "telemetry"` — a state snapshot for a module; `topic` names the module slice
  (`"cost"` | `"agents"` | `"scheduler"` | …).

The daemon's `notify`/broadcast tags each event; the desktop's `:subscribe` handler switches on
`type` → for `telemetry`, routes by `topic` to the owning module's store; for `chat`, the existing
chat append. Every subscriber gets every event and filters client-side for now.

**Future-proofing (reserved, not built).** `topic` exists so we can later add topic-*filtered*
subscriptions (`:subscribe cost`) on the same transport — the moment a second consumer with
divergent needs (e.g. a headless cost logger) shows up. Until then it's just a routing tag. This is
a strict superset of today's behavior, so it's an additive change, never a rewrite.

### Token Usage module (first wired, 2026-06-17)

Cheapest slice: the daemon already computes per-call + running `cost_usd` (M12, logged to
`sipa.cost`). After each turn the daemon broadcasts a `telemetry`/`cost` snapshot (session totals +
last-call delta: tokens in/out, `cost_usd`); the desktop's Token Usage tile renders the running
session cost + a small per-call readout. Read-only view (no controls yet).

### Background Agents module (2026-06-17)

`BackgroundDelegator` (sub-agents) keeps a per-agent record `{id, task, status}` for each detached
`delegate_background` task and pushes the **whole snapshot** (topic `agents`) on every state change —
start → `running`, finish → `done`/`error`. Full-snapshot (not incremental) so the frontend just
replaces its latest, no merge. `modules/Agents.tsx` renders the list newest-first with a status dot
(running pulses). The full result still lands in chat via the existing notify path; the tile is
status-only. Read-only for now (cancel is a later control). Fan-out `delegate` agents are *not*
shown — they block the turn and the user is already waiting; this tile is for detached work.

## First build (the backbone)

Framework only: registry + grid (drag/snap/edit) + localStorage persistence + add/remove menu, with
the **Chat** module (real, biggest) and a few **placeholder** tiles (Cost, Background Agents,
Scheduler) that say "not wired yet". GUI is compile/build-verified here; visual pass + per-module
state come next. Visual look will use the frontend-design skill.
