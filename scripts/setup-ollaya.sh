#!/bin/bash
# Idempotent setup for jev-gate's model layer on macOS (Apple silicon) or Linux:
#   1. install ollaya into ~/.local (official installer, sha256-verified) if missing
#   2. pull the default model (winnow:e4b, ~8 GB) if missing
#   3. keep a server running: macOS LaunchAgent (KEEP_ALIVE 1h) unless something already serves :11435
#   4. warm the model once and print a probe decision
# Env: JEV_GATE_MODEL (default winnow:e4b), OLLAYA_KEEP_ALIVE (default 1h), JEV_SETUP_NO_SERVICE=1
set -eu

MODEL="${JEV_GATE_MODEL:-winnow:e4b}"
KEEP="${OLLAYA_KEEP_ALIVE:-1h}"
PORT=11435
BIN="$HOME/.local/bin/ollaya"
LABEL="com.jev-gate.ollaya"
PLIST="$HOME/Library/LaunchAgents/$LABEL.plist"
status() { printf '>>> %s\n' "$*" >&2; }

# 1. binary
if [ -x "$BIN" ] || command -v ollaya >/dev/null 2>&1; then
  BIN=$(command -v ollaya 2>/dev/null || echo "$BIN")
  status "ollaya present: $BIN ($("$BIN" --version 2>/dev/null | tail -1))"
else
  status "installing ollaya into ~/.local (official installer)"
  TMP="${TMPDIR:-$HOME/.cache}/jev-gate-setup"; mkdir -p "$TMP"
  curl -fsSL https://ollaya.dev/install.sh -o "$TMP/install.sh"
  TMPDIR="$TMP" OLLAYA_INSTALL_DIR="$HOME/.local" sh "$TMP/install.sh"
  rm -rf "$TMP"
  [ -x "$BIN" ] || { echo "install failed: $BIN missing" >&2; exit 1; }
fi
export PATH="$(dirname "$BIN"):$PATH"

# 2. service
serving() { curl -sf --max-time 1 "http://127.0.0.1:$PORT/" >/dev/null 2>&1; }
if [ "${JEV_SETUP_NO_SERVICE:-0}" = "1" ]; then
  status "skipping service setup (JEV_SETUP_NO_SERVICE=1)"
elif serving; then
  status "a server already answers on :$PORT; leaving it alone (no LaunchAgent written)"
elif [ "$(uname -s)" = Darwin ]; then
  status "writing LaunchAgent $LABEL (OLLAYA_KEEP_ALIVE=$KEEP)"
  mkdir -p "$HOME/Library/LaunchAgents" "$HOME/.ollaya/logs"
  cat >"$PLIST" <<EOF
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0"><dict>
  <key>Label</key><string>$LABEL</string>
  <key>ProgramArguments</key><array><string>$BIN</string><string>serve</string></array>
  <key>EnvironmentVariables</key><dict>
    <key>OLLAYA_HOST</key><string>127.0.0.1:$PORT</string>
    <key>OLLAYA_KEEP_ALIVE</key><string>$KEEP</string>
    <key>HOME</key><string>$HOME</string>
  </dict>
  <key>RunAtLoad</key><true/>
  <key>KeepAlive</key><true/>
  <key>ProcessType</key><string>Background</string>
  <key>StandardOutPath</key><string>$HOME/.ollaya/logs/launchd.log</string>
  <key>StandardErrorPath</key><string>$HOME/.ollaya/logs/launchd.log</string>
</dict></plist>
EOF
  launchctl bootout "gui/$(id -u)/$LABEL" 2>/dev/null || true
  launchctl bootstrap "gui/$(id -u)" "$PLIST"
  for _ in $(seq 1 20); do serving && break; sleep 1; done
  serving || { echo "server did not come up; see ~/.ollaya/logs/launchd.log" >&2; exit 1; }
else
  status "starting a background server (no service manager integration on this OS)"
  (OLLAYA_KEEP_ALIVE="$KEEP" nohup "$BIN" serve >"$HOME/.ollaya/logs/serve.log" 2>&1 &)
  for _ in $(seq 1 20); do serving && break; sleep 1; done
fi

# 3. model
if "$BIN" list 2>/dev/null | awk '{print $1}' | grep -qx "$MODEL"; then
  status "model present: $MODEL"
else
  status "pulling $MODEL (winnow:e4b is ~8 GB)"
  "$BIN" pull "$MODEL"
fi

# 4. warm + probe
status "warming $MODEL (first load reads the weights from disk: up to ~20 s)"
RESP=$(curl -sS --max-time 180 "http://127.0.0.1:$PORT/v1/systemone" -H 'Content-Type: application/json' \
  -d "{\"model\":\"$MODEL\",\"state\":{\"command\":\"git push --force origin main\"},\"questions\":{\"destructive\":{\"type\":\"noul\",\"instructions\":\"Running \`command\` would irreversibly lose work.\"}}}")
printf '%s\n' "$RESP" | grep -q '"noul"' || { echo "probe failed: $RESP" >&2; exit 1; }
status "probe ok: $(printf '%s' "$RESP" | head -c 160)"
status "done. Decisions are logged under ~/.local/state/jev-gate/"
