#!/bin/sh
# One-line setup for anki-mcp-server on macOS / Linux:
#   curl -LsSf https://raw.githubusercontent.com/MeisamHakimi/anki-mcp-server/main/install.sh | sh
# Installs uv if needed (https://docs.astral.sh/uv/), then runs the interactive setup wizard, which asks
# before every change. Extra arguments are passed to the wizard (e.g. `sh install.sh --dry-run`).
set -eu

SOURCE="${ANKI_MCP_SOURCE:-anki-mcp-server @ https://github.com/MeisamHakimi/anki-mcp-server/archive/refs/heads/main.zip}"

find_uvx() {
  for c in "$(command -v uvx 2>/dev/null || true)" "$HOME/.local/bin/uvx" "$HOME/.cargo/bin/uvx" /opt/homebrew/bin/uvx /usr/local/bin/uvx; do
    if [ -n "$c" ] && [ -x "$c" ]; then echo "$c"; return 0; fi
  done
  return 1
}

if ! UVX="$(find_uvx)"; then
  echo "Installing uv (a small tool that runs Python apps; https://docs.astral.sh/uv/)..."
  curl -LsSf https://astral.sh/uv/install.sh | sh
  UVX="$(find_uvx)" || { echo "uv was installed but uvx wasn't found; open a new terminal and run this again."; exit 1; }
fi

# Read answers from the terminal even though this script arrives through a pipe (curl ... | sh).
if [ ! -t 0 ] && (exec < /dev/tty) 2>/dev/null; then
  exec "$UVX" --refresh-package anki-mcp-server --from "$SOURCE" anki-mcp-server setup "$@" < /dev/tty
fi
exec "$UVX" --refresh-package anki-mcp-server --from "$SOURCE" anki-mcp-server setup "$@"
