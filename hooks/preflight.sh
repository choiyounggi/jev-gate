#!/bin/bash
# SessionStart onboarding. Silent when the model layer is healthy. Otherwise prints ONE short
# context block telling the agent (and the user) exactly what is missing and what to run, with the
# model this machine should use. The gates keep running fail-open in the meantime.
set -u
HERE="$(cd "$(dirname "$0")" && pwd)"
URL="${JEV_GATE_URL:-http://localhost:11435/v1/systemone}"
BASE="${URL%/v1/systemone}"
CFG="${XDG_CONFIG_HOME:-$HOME/.config}/jev-gate/model"

find_ollaya() {
  for c in "${OLLAYA_BIN:-}" "$HOME/.local/bin/ollaya" /usr/local/bin/ollaya /opt/homebrew/bin/ollaya "$(command -v ollaya 2>/dev/null)"; do
    [ -n "$c" ] && [ -x "$c" ] && { echo "$c"; return; }
  done
}
BIN=$(find_ollaya)
SERVING=false; curl -sf --max-time 1 "$BASE/" >/dev/null 2>&1 && SERVING=true
# CONFIGURED: what the user chose (env or setup's file). MODEL: what the hooks will actually call.
CONFIGURED="${JEV_GATE_MODEL:-$(cat "$CFG" 2>/dev/null || true)}"
MODEL="${CONFIGURED:-winnow:e4b}"
HAVE_MODEL=false
if [ -n "$BIN" ] && "$BIN" list 2>/dev/null | awk '{print $1}' | grep -qx "$MODEL"; then HAVE_MODEL=true; fi

if $SERVING && $HAVE_MODEL; then exit 0; fi

REC=$(bash "$HERE/../scripts/recommend-model.sh" --json 2>/dev/null || echo '{}')
REC_MODEL=$(printf '%s' "$REC" | jq -r '.model // "winnow:e4b"')
REC_GB=$(printf '%s' "$REC" | jq -r '.download_gb // "?"')
REC_WHY=$(printf '%s' "$REC" | jq -r '.reason // ""')
MEM=$(printf '%s' "$REC" | jq -r '.machine.memory_gb // "?"')

echo "jev-gate onboarding — the local decision model is not ready, so the Bash gate and the Stop gate run with deterministic rules only (fail-open, nothing is blocked by this)."
if [ -z "$BIN" ]; then
  echo "  missing: ollaya (the local decision-model server)"
elif ! $SERVING; then
  echo "  missing: a running server at $BASE (ollaya is installed at $BIN)"
fi
if [ -n "$CONFIGURED" ] && ! $HAVE_MODEL; then
  echo "  missing: configured model '$CONFIGURED' is not pulled"
elif [ -z "$CONFIGURED" ]; then
  echo "  recommended model for this machine (${MEM} GB memory): $REC_MODEL (~${REC_GB} GB download) — $REC_WHY"
  echo "  alternatives: winnow:e4b 8 GB (best measured) · decider 4 GB · decider:0.8b 1.5 GB · laya 1.5 GB (fast, weak on shell risk)"
fi
echo "  To set it up, run the skill: /jev-gate:setup  (it asks which model to pull, then installs, downloads and verifies; JEV_GATE_MODEL=<name> overrides)"
exit 0
