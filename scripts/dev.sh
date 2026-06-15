#!/usr/bin/env zsh
# Launch S.I.P.A. with one command: the daemon (foreground — keeps its REPL, cost logs, and
# Ctrl-D-saves-session) plus the desktop app (background, logs to a file). Quitting the daemon
# (Ctrl-D / Ctrl-C) tears down the app too.

set -e
cd "${0:A:h:h}" # repo root (this script lives in scripts/)

echo "▸ starting desktop app in the background (logs → /tmp/sipa-desktop.log)…"
(cd desktop && cargo tauri dev) >/tmp/sipa-desktop.log 2>&1 &
app_pid=$!
trap 'kill $app_pid 2>/dev/null' EXIT

echo "▸ starting daemon — first launch downloads the embedding model, give it a few seconds."
echo "  Ctrl-D quits both."
uv run sipa
