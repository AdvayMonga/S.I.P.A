# S.I.P.A. desktop

An extremely basic Tauri v2 shell that talks to the running daemon over its Unix socket.

## Run

1. Start the daemon from the repo root: `make run` (binds `data/sipa.sock`).
2. Point the app at that socket and launch dev:
   ```sh
   cd desktop
   SIPA_SOCKET="$(cd .. && pwd)/data/sipa.sock" cargo tauri dev
   ```

`SIPA_SOCKET` overrides the socket path (defaults to `data/sipa.sock` relative to cwd).

## Layout

- `src/` — static frontend (no bundler): `index.html`, `main.js`, `style.css`.
- `src-tauri/` — the Rust shell. `src/lib.rs` holds the `ask` command (bridges to the socket).

Production bundling needs icons (`src-tauri/icons/`) — not set up yet; dev runs without them.
