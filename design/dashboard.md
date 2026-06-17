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

## First build (the backbone)

Framework only: registry + grid (drag/snap/edit) + localStorage persistence + add/remove menu, with
the **Chat** module (real, biggest) and a few **placeholder** tiles (Cost, Background Agents,
Scheduler) that say "not wired yet". GUI is compile/build-verified here; visual pass + per-module
state come next. Visual look will use the frontend-design skill.
