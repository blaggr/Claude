#!/usr/bin/env bash
# Shared helpers for the AVAL macOS scripts. Sourced, not run.

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
OLLAMA_ADDR="127.0.0.1:11434"
LAUNCH_LABEL="edu.ucla.aval.ollama"
LAUNCH_PLIST="$HOME/Library/LaunchAgents/$LAUNCH_LABEL.plist"
OLLAMA_LOG="$HOME/Library/Logs/aval-ollama.log"
GOOSE_CONFIG_DIR="$HOME/.config/goose"

say()  { printf '\n==> %s\n' "$*"; }
pass() { printf '  PASS  %s\n' "$*"; }
warn() { printf '  WARN  %s\n' "$*"; WARNINGS=$((${WARNINGS:-0} + 1)); }
fail() { printf '  FAIL  %s\n' "$*"; FAILURES=$((${FAILURES:-0} + 1)); }
die()  { printf '\nERROR: %s\n' "$*" >&2; exit 1; }

# conf_get KEY FILE -> value of KEY=VALUE (empty if unset)
conf_get() {
  grep -E "^$1=" "$2" 2>/dev/null | head -n1 | cut -d= -f2-
}

# version_ge A B -> true if A >= B (numeric dotted versions)
version_ge() {
  local IFS=.
  local -a a b
  read -r -a a <<<"$1"
  read -r -a b <<<"$2"
  local i
  for i in 0 1 2 3; do
    local x=${a[i]:-0} y=${b[i]:-0}
    x=${x%%[!0-9]*}; y=${y%%[!0-9]*}
    (( 10#${x:-0} > 10#${y:-0} )) && return 0
    (( 10#${x:-0} < 10#${y:-0} )) && return 1
  done
  return 0
}

ram_gb() {
  echo $(( $(sysctl -n hw.memsize) / 1024 / 1024 / 1024 ))
}

# pick_model -> prints "TIER TAG EXPECTED_ID" for this machine's RAM
pick_model() {
  local ram; ram=$(ram_gb)
  awk -v ram="$ram" '
    /^[[:space:]]*#/ || NF < 4 { next }
    $2 <= ram && $2 >= best { best = $2; line = $1 " " $3 " " $4 }
    END { if (line == "") exit 1; print line }
  ' "$REPO_ROOT/models.conf"
}

brew_bin() {
  if command -v brew >/dev/null 2>&1; then command -v brew
  elif [ -x /opt/homebrew/bin/brew ]; then echo /opt/homebrew/bin/brew
  elif [ -x /usr/local/bin/brew ]; then echo /usr/local/bin/brew
  fi
}

ollama_bin() {
  local b; b=$(brew_bin)
  [ -n "$b" ] && [ -x "$("$b" --prefix)/bin/ollama" ] && { echo "$("$b" --prefix)/bin/ollama"; return; }
  command -v ollama 2>/dev/null
}

ollama_up() {
  curl -fsS --max-time 2 "http://$OLLAMA_ADDR/api/version" >/dev/null 2>&1
}

ollama_version() {
  curl -fsS --max-time 2 "http://$OLLAMA_ADDR/api/version" 2>/dev/null \
    | grep -Eo '[0-9]+\.[0-9]+\.[0-9]+' | head -n1
}
