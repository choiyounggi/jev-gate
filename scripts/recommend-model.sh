#!/bin/bash
# Recommend a decision model for THIS machine, by memory (Apple silicon unified memory / system RAM)
# and NVIDIA VRAM when present. Prints human text, or JSON with --json.
#
# Tiers (download size ≈ what ollaya pulls; accuracy = typed-decisions self-reported by each author,
# except winnow:e4b which jev-gate measured on its own 50-case set):
#   winnow:e4b    ~8 GB   Gemma-4 7.5B Q8   0.722 (jev-gate: shell risk 84%, agent report 100%)  ≥ 24 GB RAM or ≥ 12 GB VRAM
#   decider       ~4 GB   Qwen3.5 2.2B      0.680 (unmeasured by jev-gate)                         16–23 GB
#   decider:0.8b  ~1.5 GB Qwen3.5 0.75B     (unmeasured)                                            8–15 GB
#   laya          ~1.5 GB ModernBERT/mmBERT 0.361 — fast (~100 ms) but weak on shell judgments      < 8 GB or CPU-only fallback
#
# Test overrides: JEV_FAKE_OS (Darwin|Linux), JEV_FAKE_ARCH (arm64|x86_64), JEV_FAKE_MEM_GB, JEV_FAKE_VRAM_GB ("" = no GPU)
set -u

OS="${JEV_FAKE_OS:-$(uname -s)}"
ARCH="${JEV_FAKE_ARCH:-$(uname -m)}"

mem_gb() {
  if [ -n "${JEV_FAKE_MEM_GB:-}" ]; then echo "$JEV_FAKE_MEM_GB"; return; fi
  case $OS in
    Darwin) echo $(( $(sysctl -n hw.memsize 2>/dev/null || echo 0) / 1073741824 )) ;;
    Linux)  awk '/MemTotal/ {printf "%d", $2/1048576}' /proc/meminfo 2>/dev/null || echo 0 ;;
    *) echo 0 ;;
  esac
}
vram_gb() {
  if [ -n "${JEV_FAKE_VRAM_GB+x}" ]; then echo "${JEV_FAKE_VRAM_GB}"; return; fi
  command -v nvidia-smi >/dev/null 2>&1 || { echo ""; return; }
  nvidia-smi --query-gpu=memory.total --format=csv,noheader,nounits 2>/dev/null | sort -n | tail -1 | awk '{printf "%d", $1/1024}'
}

MEM=$(mem_gb); VRAM=$(vram_gb)
APPLE=false; [ "$OS" = Darwin ] && [ "$ARCH" = arm64 ] && APPLE=true

if [ -n "$VRAM" ] && [ "$VRAM" -ge 12 ]; then
  MODEL=winnow:e4b; SIZE=8; TIER=gpu
  REASON="NVIDIA GPU with ${VRAM} GB VRAM: the 8 GB model fits on the GPU"
elif [ "$MEM" -ge 24 ]; then
  MODEL=winnow:e4b; SIZE=8; TIER=large
  REASON="${MEM} GB memory: room for the 8 GB model (it pins ~8 GB while loaded, unloads after idle)"
elif [ "$MEM" -ge 16 ]; then
  MODEL=decider; SIZE=4; TIER=medium
  REASON="${MEM} GB memory: an 8 GB model would swap alongside an IDE and a browser; the ~4 GB 2.2B model is the safe default"
elif [ "$MEM" -ge 8 ]; then
  MODEL=decider:0.8b; SIZE=1.5; TIER=small
  REASON="${MEM} GB memory: only a ~1.5 GB model leaves room for your work"
else
  MODEL=laya; SIZE=1.5; TIER=minimal
  REASON="${MEM} GB memory: the encoder model is the only one that fits; fast, but weak on shell-risk judgments"
fi
if [ "$OS" = Linux ] && [ -z "$VRAM" ] && [ "$TIER" = large ]; then
  REASON="$REASON; no NVIDIA GPU, so the 7.5B model runs on the CPU at a few seconds per judgment — consider decider if that is too slow"
fi

if [ "${1:-}" = "--json" ]; then
  jq -cn --arg model "$MODEL" --argjson size "$SIZE" --arg tier "$TIER" --arg reason "$REASON" \
     --arg os "$OS" --arg arch "$ARCH" --argjson mem "$MEM" --arg vram "$VRAM" --argjson apple "$APPLE" '{
    model: $model, download_gb: $size, tier: $tier, reason: $reason,
    machine: {os: $os, arch: $arch, memory_gb: $mem, nvidia_vram_gb: ($vram | if . == "" then null else tonumber end), apple_silicon: $apple},
    alternatives: [
      {model: "winnow:e4b",  download_gb: 8,   note: "best measured: shell risk 84% (0 dangerous misses), agent report 100%; needs ~8 GB free while loaded"},
      {model: "decider",     download_gb: 4,   note: "Qwen3.5 2.2B, typed-decisions 0.680 (author-reported), not yet measured by jev-gate"},
      {model: "decider:0.8b",download_gb: 1.5, note: "Qwen3.5 0.75B, lightest decoder; unmeasured"},
      {model: "laya",        download_gb: 1.5, note: "~100 ms encoder, 100+ languages; measured weak on shell judgments (36-68%)"}
    ]}'
else
  printf 'Recommended model: %s (~%s GB download)\n  %s\n' "$MODEL" "$SIZE" "$REASON"
  printf 'Machine: %s %s, %s GB memory%s\n' "$OS" "$ARCH" "$MEM" "${VRAM:+, NVIDIA ${VRAM} GB VRAM}"
  printf 'Alternatives: winnow:e4b (8 GB, best measured) · decider (4 GB) · decider:0.8b (1.5 GB) · laya (1.5 GB, fast, weak on shell risk)\n'
fi
