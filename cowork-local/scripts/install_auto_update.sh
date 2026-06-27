#!/usr/bin/env bash
# Install (or remove) a macOS LaunchAgent that checks for newer Qwen/GLM models
# daily and pulls them, so Cowork Local stays on the latest release without you
# doing anything.
#
# Usage:
#   ./scripts/install_auto_update.sh                  # daily at 03:00, primary=qwen
#   ./scripts/install_auto_update.sh --primary glm    # prefer GLM as the default
#   ./scripts/install_auto_update.sh --hour 9         # run daily at 09:00
#   ./scripts/install_auto_update.sh --uninstall      # remove the schedule
set -euo pipefail

LABEL="com.coworklocal.modelupdater"
PLIST="$HOME/Library/LaunchAgents/$LABEL.plist"
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
UPDATER="$SCRIPT_DIR/update_models.py"

PRIMARY="qwen"
HOUR=3
UNINSTALL=0
while [[ $# -gt 0 ]]; do
  case "$1" in
    --primary) PRIMARY="$2"; shift 2 ;;
    --hour) HOUR="$2"; shift 2 ;;
    --uninstall) UNINSTALL=1; shift ;;
    *) echo "Unknown option: $1" >&2; exit 1 ;;
  esac
done

uid="$(id -u)"

if [[ "$UNINSTALL" == "1" ]]; then
  launchctl bootout "gui/$uid/$LABEL" 2>/dev/null || true
  rm -f "$PLIST"
  echo "Removed auto-update schedule ($LABEL)."
  exit 0
fi

PYTHON="$(command -v python3 || true)"
[[ -z "$PYTHON" ]] && { echo "python3 not found on PATH." >&2; exit 1; }

# Build a PATH the agent can use to find ollama (Homebrew on Intel + Apple
# Silicon) and python, since LaunchAgents start with a minimal environment.
AGENT_PATH="/opt/homebrew/bin:/usr/local/bin:/usr/bin:/bin:$HOME/.cargo/bin"

mkdir -p "$HOME/Library/LaunchAgents" "$HOME/.cowork-local"

cat > "$PLIST" <<PLISTEOF
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
  <key>Label</key>
  <string>$LABEL</string>
  <key>ProgramArguments</key>
  <array>
    <string>$PYTHON</string>
    <string>$UPDATER</string>
    <string>--primary</string>
    <string>$PRIMARY</string>
  </array>
  <key>EnvironmentVariables</key>
  <dict>
    <key>PATH</key>
    <string>$AGENT_PATH</string>
    <key>OLLAMA_HOST</key>
    <string>http://127.0.0.1:11434</string>
  </dict>
  <key>StartCalendarInterval</key>
  <dict>
    <key>Hour</key><integer>$HOUR</integer>
    <key>Minute</key><integer>0</integer>
  </dict>
  <key>RunAtLoad</key>
  <true/>
  <key>StandardOutPath</key>
  <string>$HOME/.cowork-local/updater.log</string>
  <key>StandardErrorPath</key>
  <string>$HOME/.cowork-local/updater.log</string>
</dict>
</plist>
PLISTEOF

# Reload cleanly.
launchctl bootout "gui/$uid/$LABEL" 2>/dev/null || true
launchctl bootstrap "gui/$uid" "$PLIST"

echo "Installed auto-update schedule:"
echo "  label:   $LABEL"
echo "  runs:    daily at ${HOUR}:00 (and at login), primary family = $PRIMARY"
echo "  plist:   $PLIST"
echo "  log:     $HOME/.cowork-local/updater.log"
echo
echo "It just ran once (RunAtLoad). Check the log to see what it pulled:"
echo "  tail -f $HOME/.cowork-local/updater.log"
