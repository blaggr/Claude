#!/usr/bin/env bash
# AVAL Local AI Stack: security and configuration check for macOS.
# Prints PASS / WARN / FAIL. Paste the output to the maintainer.
set -uo pipefail
# shellcheck source=common.sh
source "$(dirname "$0")/common.sh"
FAILURES=0; WARNINGS=0
VERSIONS="$REPO_ROOT/versions.conf"

echo
echo "AVAL Local AI Stack check  |  $(date '+%Y-%m-%d %H:%M')  |  $(scutil --get ComputerName 2>/dev/null || hostname)"
echo "Stack $(conf_get STACK_VERSION "$VERSIONS")  |  macOS $(sw_vers -productVersion)  |  $(uname -m)  |  $(ram_gb) GB RAM"

# Ollama running, version, bind address
if ollama_up; then
  VER=$(ollama_version); MIN=$(conf_get OLLAMA_MIN_VERSION "$VERSIONS"); TESTED=$(conf_get OLLAMA_TESTED_VERSION "$VERSIONS")
  if version_ge "$VER" "$MIN"; then pass "Ollama $VER (minimum $MIN)"; else fail "Ollama $VER is below minimum $MIN"; fi
  [ -n "$TESTED" ] && [ "$VER" != "$TESTED" ] && warn "Ollama $VER differs from the tested version $TESTED"
else
  fail "Ollama is not running on $OLLAMA_ADDR"
fi

LISTEN=$(lsof -nP -iTCP:11434 -sTCP:LISTEN 2>/dev/null | awk 'NR > 1 { print $9 }' | sort -u)
if [ -z "$LISTEN" ]; then
  fail "Nothing is listening on port 11434"
elif echo "$LISTEN" | grep -vqE '^(127\.0\.0\.1|\[::1\]):11434$'; then
  fail "Ollama is reachable from the network: $LISTEN"
else
  pass "Ollama listens on loopback only ($LISTEN)"
fi

# Cloud disabled
if grep -q '"disable_ollama_cloud": *true' "$HOME/.ollama/server.json" 2>/dev/null; then
  pass "server.json disables Ollama cloud"
else
  fail "~/.ollama/server.json does not disable Ollama cloud"
fi
if grep -q 'cloud disabled: true' "$OLLAMA_LOG" 2>/dev/null; then
  pass "Ollama log confirms cloud disabled"
else
  warn "Could not confirm 'cloud disabled: true' in $OLLAMA_LOG (log may have rotated)"
fi

# No competing Ollama app with its own updater
if pgrep -x Ollama >/dev/null; then warn "Ollama.app is running; it has its own auto-updater. Quit it and remove it."; else pass "Ollama.app not running"; fi
launchctl print "gui/$(id -u)/$LAUNCH_LABEL" >/dev/null 2>&1 && pass "AVAL Ollama LaunchAgent loaded" || fail "AVAL Ollama LaunchAgent not loaded"

# Model
if PICK=$(pick_model); then
  read -r TIER MODEL EXPECTED_ID <<<"$PICK"
  OLLAMA=$(ollama_bin)
  ID=$("$OLLAMA" list 2>/dev/null | awk -v m="$MODEL" '$1 == m { print $2 }')
  if [ -z "$ID" ]; then fail "Model $MODEL (tier $TIER) is not installed"
  elif [ "$EXPECTED_ID" = "-" ]; then warn "Model $MODEL present (ID $ID); manifest ID not pinned yet"
  elif [ "$ID" = "$EXPECTED_ID" ]; then pass "Model $MODEL matches pinned ID $ID"
  else fail "Model $MODEL ID $ID does not match pinned $EXPECTED_ID"; fi
fi

# goose
if [ -d "/Applications/Goose.app" ] || brew list --cask block-goose >/dev/null 2>&1; then pass "goose Desktop installed"; else fail "goose Desktop not installed"; fi
CFG="$GOOSE_CONFIG_DIR/config.yaml"
if [ -f "$CFG" ]; then
  grep -qE '^GOOSE_MODE: *"?approve"?' "$CFG" && pass "goose asks before every tool call (approve mode)" || fail "goose is not in approve mode"
  grep -qE '^GOOSE_TELEMETRY_ENABLED: *false' "$CFG" && pass "goose telemetry off" || fail "goose telemetry not disabled"
  grep -qE '^active_provider: *ollama' "$CFG" && pass "goose uses local Ollama" || fail "goose provider is not Ollama"
  grep -qE '^GOOSE_ALLOWLIST:' "$CFG" && pass "goose extension allowlist set" || warn "goose extension allowlist not set"
else
  fail "goose config not found at $CFG"
fi

# OS controls (report only)
fdesetup status 2>/dev/null | grep -q "FileVault is On" && pass "FileVault on" || fail "FileVault is off: System Settings > Privacy & Security > FileVault"
FW=$(/usr/libexec/ApplicationFirewall/socketfilterfw --getglobalstate 2>/dev/null || true)
echo "$FW" | grep -qi "enabled" && pass "macOS firewall on" || warn "macOS firewall off: System Settings > Network > Firewall"

echo
echo "Result: $FAILURES failure(s), $WARNINGS warning(s)"
[ "$FAILURES" -eq 0 ]
