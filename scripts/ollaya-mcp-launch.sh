#!/bin/bash
# Launch `ollaya mcp` (stdio MCP server) wherever ollaya is installed. Claude Code starts plugin MCP
# servers with a minimal PATH, so the usual install locations are searched explicitly.
set -u
for c in "${OLLAYA_BIN:-}" "$HOME/.local/bin/ollaya" /usr/local/bin/ollaya /opt/homebrew/bin/ollaya "$(command -v ollaya 2>/dev/null)"; do
  if [ -n "$c" ] && [ -x "$c" ]; then exec "$c" mcp; fi
done
echo "jev-gate: ollaya is not installed. Run the jev-gate:setup skill (or scripts/setup-ollaya.sh)." >&2
exit 1
