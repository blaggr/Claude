#!/usr/bin/env bash
# AVAL Local AI Stack installer / updater for macOS.
# Safe to re-run: the same script installs, repairs, and updates.
set -euo pipefail
# shellcheck source=common.sh
source "$(dirname "$0")/common.sh"

VERSIONS="$REPO_ROOT/versions.conf"
STACK_VERSION=$(conf_get STACK_VERSION "$VERSIONS")
OLLAMA_MIN=$(conf_get OLLAMA_MIN_VERSION "$VERSIONS")
CONTEXT_TOKENS=$(conf_get CONTEXT_TOKENS "$VERSIONS")
ALLOWLIST_URL=$(conf_get GOOSE_ALLOWLIST_URL "$VERSIONS")
RECIPE_REPO=$(conf_get GOOSE_RECIPE_REPO "$VERSIONS")

echo "AVAL Local AI Stack $STACK_VERSION for macOS"
[ "$(uname -s)" = "Darwin" ] || die "This script is for macOS."
[ "$(id -u)" -ne 0 ] || die "Run this as yourself, not with sudo."

# 1. Homebrew --------------------------------------------------------------
say "Checking Homebrew"
BREW=$(brew_bin)
if [ -z "$BREW" ]; then
  cat <<'MSG'
Homebrew is not installed. Install it with the official .pkg installer:
  https://github.com/Homebrew/brew/releases/latest   (download Homebrew-<version>.pkg)
Then run this installer again.
MSG
  open "https://github.com/Homebrew/brew/releases/latest" || true
  exit 1
fi
eval "$("$BREW" shellenv)"
brew update --quiet

# 2. Ollama (Homebrew formula: server only, no menu-bar app, no self-updater)
say "Installing / updating Ollama"
if [ -d "/Applications/Ollama.app" ]; then
  echo "  Note: /Applications/Ollama.app is installed. It has its own auto-updater and"
  echo "  menu-bar server, which this stack replaces. Quit it and move it to the Trash"
  echo "  (your downloaded models are kept in ~/.ollama)."
  osascript -e 'quit app "Ollama"' >/dev/null 2>&1 || true
fi
if brew list --formula ollama >/dev/null 2>&1; then brew upgrade ollama || true; else brew install ollama; fi
brew services stop ollama >/dev/null 2>&1 || true   # we run our own LaunchAgent instead
OLLAMA=$(ollama_bin)
[ -n "$OLLAMA" ] || die "ollama binary not found after install."

# 3. Local-only settings ----------------------------------------------------
say "Applying local-only Ollama settings"
mkdir -p "$HOME/.ollama"
if [ -f "$HOME/.ollama/server.json" ] && ! cmp -s "$HOME/.ollama/server.json" "$REPO_ROOT/config/ollama/server.json"; then
  cp "$HOME/.ollama/server.json" "$HOME/.ollama/server.json.bak-$(date +%Y%m%d%H%M%S)"
fi
cp "$REPO_ROOT/config/ollama/server.json" "$HOME/.ollama/server.json"

mkdir -p "$HOME/Library/LaunchAgents" "$HOME/Library/Logs"
cat >"$LAUNCH_PLIST" <<PLIST
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
  <key>Label</key><string>$LAUNCH_LABEL</string>
  <key>ProgramArguments</key>
  <array><string>$OLLAMA</string><string>serve</string></array>
  <key>EnvironmentVariables</key>
  <dict>
    <key>OLLAMA_HOST</key><string>$OLLAMA_ADDR</string>
    <key>OLLAMA_NO_CLOUD</key><string>1</string>
  </dict>
  <key>RunAtLoad</key><true/>
  <key>KeepAlive</key><true/>
  <key>StandardOutPath</key><string>$OLLAMA_LOG</string>
  <key>StandardErrorPath</key><string>$OLLAMA_LOG</string>
</dict>
</plist>
PLIST
launchctl bootout "gui/$(id -u)/$LAUNCH_LABEL" >/dev/null 2>&1 || true
: >"$OLLAMA_LOG"
launchctl bootstrap "gui/$(id -u)" "$LAUNCH_PLIST"

printf '  Waiting for Ollama to start'
for _ in $(seq 1 30); do ollama_up && break; printf '.'; sleep 1; done; echo
ollama_up || die "Ollama did not start. See $OLLAMA_LOG"

VER=$(ollama_version)
version_ge "$VER" "$OLLAMA_MIN" || die "Ollama $VER is older than the required $OLLAMA_MIN. Run 'brew upgrade ollama' and retry."
echo "  Ollama $VER running on $OLLAMA_ADDR"

# 4. Model for this machine -------------------------------------------------
say "Choosing a model for this Mac ($(ram_gb) GB RAM)"
PICK=$(pick_model) || die "This Mac has less RAM than the smallest tier in models.conf."
read -r TIER MODEL EXPECTED_ID <<<"$PICK"
echo "  Tier $TIER -> $MODEL"
"$OLLAMA" pull "$MODEL"

OTHERS=$("$OLLAMA" list | awk -v keep="$MODEL" 'NR > 1 && $1 != keep { print $1 }')
if [ -n "$OTHERS" ]; then
  echo "  Other models on this Mac that are not in the AVAL manifest:"
  printf '    %s\n' $OTHERS
  read -r -p "  Remove them to free disk space? [y/N] " ans </dev/tty || ans=n
  if [[ "$ans" =~ ^[Yy]$ ]]; then for m in $OTHERS; do "$OLLAMA" rm "$m"; done; fi
fi

# 5. goose Desktop ----------------------------------------------------------
say "Installing / updating goose Desktop"
if brew list --cask block-goose >/dev/null 2>&1; then brew upgrade --cask block-goose || true; else brew install --cask block-goose; fi

say "Writing team goose configuration"
mkdir -p "$GOOSE_CONFIG_DIR"
CFG="$GOOSE_CONFIG_DIR/config.yaml"
[ -f "$CFG" ] && cp "$CFG" "$CFG.bak-$(date +%Y%m%d%H%M%S)"
ALLOW_LINE="# GOOSE_ALLOWLIST: (not set; see docs/QUESTIONS.md Q6)"
[ -n "$ALLOWLIST_URL" ] && ALLOW_LINE="GOOSE_ALLOWLIST: \"$ALLOWLIST_URL\""
RECIPE_LINE="# GOOSE_RECIPE_GITHUB_REPO: (not set)"
[ -n "$RECIPE_REPO" ] && RECIPE_LINE="GOOSE_RECIPE_GITHUB_REPO: \"$RECIPE_REPO\""
sed_escape() { printf '%s' "$1" | sed -e 's/[|&\\]/\\&/g'; }
ALLOW_LINE=$(sed_escape "$ALLOW_LINE"); RECIPE_LINE=$(sed_escape "$RECIPE_LINE")
sed -e "s|__MODEL__|$MODEL|" \
    -e "s|__CONTEXT_TOKENS__|$CONTEXT_TOKENS|" \
    -e "s|__ALLOWLIST_LINE__|$ALLOW_LINE|" \
    -e "s|__RECIPE_LINE__|$RECIPE_LINE|" \
    "$REPO_ROOT/config/goose/config.yaml.template" >"$CFG"
chmod 600 "$CFG"

# GUI apps do not read shell profiles; set the allowlist for the login session too.
[ -n "$ALLOWLIST_URL" ] && launchctl setenv GOOSE_ALLOWLIST "$ALLOWLIST_URL"

# 6. Verify -----------------------------------------------------------------
bash "$REPO_ROOT/scripts/mac/verify.sh"
echo
echo "Done. Open goose from Applications. Read docs/USING-GOOSE.md first."
