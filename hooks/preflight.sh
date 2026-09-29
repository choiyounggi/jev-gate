#!/bin/bash
# SessionStart: one line of context when the decision server is not answering, so the agent knows
# both gates are running fail-open (deterministic rules only) and how to fix it. Silent when healthy.
set -u
URL="${JEV_GATE_URL:-http://localhost:11435/v1/systemone}"
BASE="${URL%/v1/systemone}"
if curl -sf --max-time 1 "$BASE/" >/dev/null 2>&1; then
  exit 0
fi
cat <<'EOF'
jev-gate: the local decision server (ollaya, http://localhost:11435) is not answering. The Bash gate
and the Stop gate keep working with deterministic rules only and never block on this. To restore the
model layer run the `jev-gate:setup` skill, or: `ollaya serve` (installs: https://ollaya.dev).
EOF
exit 0
