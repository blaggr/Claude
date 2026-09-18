#!/usr/bin/env bash
# <xbar.title>AI Trading Agent</xbar.title>
# <xbar.version>v1.0</xbar.version>
# <xbar.desc>Menu-bar status for the paper trading agent: equity, P&L, positions, running state.</xbar.desc>
# <swiftbar.hideAbout>true</swiftbar.hideAbout>
#
# SwiftBar plugin. The filename "30s" sets the refresh interval (every 30s).
# Install: see agent/widget/README.md.
#
# It sources your agent.env (for the Alpaca keys), then runs status.py in the
# project's virtualenv. Override the two paths below if your layout differs.
REPO="${TRADING_AGENT_REPO:-$HOME/Claude}"
VENV="${TRADING_AGENT_VENV:-$REPO/.venv}"

ENV_FILE="$REPO/agent/deploy/agent.env"
[ -f "$ENV_FILE" ] && { set -a; . "$ENV_FILE"; set +a; }

PY="$VENV/bin/python3"
[ -x "$PY" ] || PY="$(command -v python3)"

"$PY" "$REPO/agent/widget/status.py" --swiftbar --interval "${POLL_SECONDS:-60}" 2>/dev/null \
  || { echo "⚠️ agent widget"; echo "---"; echo "status.py failed — check $REPO and the venv"; }
