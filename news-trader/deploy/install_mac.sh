#!/usr/bin/env bash
# install_mac.sh — copy the launchd plist to ~/Library/LaunchAgents/
#
# This script does NOT auto-load the agent. You must review and fill
# every <FILL ME> placeholder in the plist (and fix the absolute path)
# before loading. See DEPLOY_MAC.md for the full runbook.
set -euo pipefail

PLIST="com.user.newstrader.plist"
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SRC="$SCRIPT_DIR/$PLIST"
DEST="$HOME/Library/LaunchAgents/$PLIST"

if [ ! -f "$SRC" ]; then
    echo "ERROR: $SRC not found. Run this script from the deploy/ directory or use its full path."
    exit 1
fi

# Warn if any placeholders are still unfilled
if grep -q '<FILL ME' "$SRC" || grep -q '<ABSOLUTE PATH' "$SRC"; then
    echo ""
    echo "WARNING: The plist still contains unfilled placeholders."
    echo "Edit $SRC and replace every <FILL ME> and <ABSOLUTE PATH> before loading."
    echo ""
fi

mkdir -p "$HOME/Library/LaunchAgents"
cp "$SRC" "$DEST"
echo "Copied $PLIST -> $DEST"
echo ""
echo "Review the plist, fill all placeholders, then run:"
echo ""
echo "    launchctl load $DEST"
echo ""
echo "To check the worker is running:"
echo "    launchctl list | grep newstrader"
echo "    tail -f /tmp/newstrader.log"
echo ""
echo "To stop (preferred — graceful kill switch):"
echo "    touch \$(dirname \"\$(grep ProgramArguments -A2 \"$DEST\" | grep worker.py | tr -d ' <string>')\")/KILL"
echo ""
echo "To unload the agent entirely:"
echo "    launchctl unload $DEST"
