# design/desktop.md

An extremely basic Tauri v2 desktop shell — a thin client over the daemon's Unix socket, proving the
front-end seam (VISION §10 "Desktop app"). Lives in `desktop/`, outside the Python package.

## Shape

```
webview (src/) ──invoke("ask", {message})──▶ Rust (src-tauri/lib.rs) ──UnixStream──▶ daemon socket
```

- **Frontend** (`desktop/src/`, no bundler): `index.html` + `main.js` + `style.css`. A chat log + a
  composer; `main.js` calls `invoke("ask", …)` via the global `window.__TAURI__` (enabled by
  `app.withGlobalTauri`). Served statically through `frontendDist: "../src"`.
- **Backend** (`desktop/src-tauri/`): the `ask(message)` command opens a `UnixStream` to the socket
  (`SIPA_SOCKET` env, default `~/.sipa/sipa.sock`), writes the line, returns the reply line. One
  connection per message — the daemon shares one `Conversation` across connections, so continuity
  holds regardless.

## Run

Daemon first (`make run`), then `cd desktop && cargo tauri dev` (both default to `~/.sipa/sipa.sock`). See
`desktop/README.md`.

## Scope / deferred

- Stateless per-message connect (simple); a persistent connection + streaming is a later refinement.
- No production bundling: needs real icons (`src-tauri/icons/` has only a generated placeholder).
- The socket transport is the contract; richer protocol (history, cost, structured events) is later.
