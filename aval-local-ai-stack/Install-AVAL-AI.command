#!/usr/bin/env bash
# Double-click to install or update the AVAL Local AI Stack on macOS.
cd "$(dirname "$0")" || exit 1
bash scripts/mac/install.sh
echo
read -r -p "Press Return to close this window." _
