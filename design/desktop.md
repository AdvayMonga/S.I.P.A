# design/desktop.md

A Tauri v2 desktop **dashboard** — a thin client over the daemon's Unix socket, the front-end seam
(VISION §10 "Desktop app"). Lives in `desktop/`, outside the Python package.

## Stack

**React + Vite + TypeScript**, styled with our own CSS design tokens (no UI kit, to keep the
operator-console look distinctive). Self-hosted variable fonts (JetBrains Mono for console
labels/data, Public Sans for chat body). Tauri dev uses Vite's dev server (`devUrl`); builds bundle
to `dist/`.

## Shape

```
React (src/) ──invoke("ask", {message})──▶ Rust (src-tauri/lib.rs) ──UnixStream──▶ daemon socket
```

- **Frontend** (`desktop/src/`): a dashboard — `StatusBar` (wordmark + the state-pulse signature +
  session cost) · `PanelGrid` of configurable `PANELS` (Cost, Open Tasks, Autobuild — placeholder
  empty states for now; each gets a live data source later) · `Chat` (transcript + composer) wired
  to the daemon via `invoke("ask", …)` from `@tauri-apps/api/core`. Layout = status · panels ·
  transcript · composer (chat owns the center/bottom).
- **Signature:** `StatePulse` — a dot that encodes daemon state; warm + pulsing while a request is
  in flight (real, derived from the chat round-trip), cool when idle.
- **Backend** (`desktop/src-tauri/`): the `ask(message)` command opens a `UnixStream` to the socket
  (`SIPA_SOCKET` env, default `~/.sipa/sipa.sock`), writes the line, returns the reply line. One
  connection per message — the daemon shares one `Conversation` across connections, so continuity
  holds regardless. A **`subscribe_loop`** (spawned at setup) holds a persistent `:subscribe`
  connection and emits each proactive push (background results, scheduled tasks) as a `sipa-push`
  Tauri event; the frontend `Chat` listens and appends them as messages. Reconnects if the daemon
  isn't up / the link drops.

## Run

Daemon first (`make run`), then `cd desktop && cargo tauri dev` (both default to `~/.sipa/sipa.sock`). See
`desktop/README.md`.

## Scope / deferred

- Panels render placeholder/empty states — live data (cost, open tasks via existing daemon tools) is
  a small follow-up; autobuild waits on siloop.
- Stateless per-message connect; a persistent connection + streaming chat is a later refinement.
- No production bundling: needs real icons (`src-tauri/icons/` has only a generated placeholder).
- No tray icon / global hotkey yet (VISION §10 calls for them) — next desktop pass.
- The socket transport is the contract; richer protocol (telemetry push, structured events) is later.
