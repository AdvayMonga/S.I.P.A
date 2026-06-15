# S.I.P.A. desktop

An extremely basic Tauri v2 shell that talks to the running daemon over its Unix socket.

## Run

1. Start the daemon from the repo root: `make run` (binds `~/.sipa/sipa.sock`).
2. Launch the app:
   ```sh
   cd desktop
   cargo tauri dev
   ```

Both default to `~/.sipa/sipa.sock`, so no configuration is needed. `SIPA_SOCKET` overrides the
socket path if you want a different location.

## Layout

- `src/` — static frontend (no bundler): `index.html`, `main.js`, `style.css`.
- `src-tauri/` — the Rust shell. `src/lib.rs` holds the `ask` command (bridges to the socket).

Production bundling needs icons (`src-tauri/icons/`) — not set up yet; dev runs without them.
