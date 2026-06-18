#!/usr/bin/env bash
# Run the always-on agent driver in a detached tmux session that auto-restarts
# on crash. Use this when you don't have (or don't want) systemd — e.g. macOS,
# a shared box, or a quick unattended run on a VPS.
#
#   ./agent/deploy/run_tmux.sh start     # create/restart the session
#   ./agent/deploy/run_tmux.sh attach    # watch it live (Ctrl-b d to detach)
#   ./agent/deploy/run_tmux.sh stop       # stop the driver (positions left as-is)
#   ./agent/deploy/run_tmux.sh kill       # flatten everything + stop
#   ./agent/deploy/run_tmux.sh status     # is it running?
#
# Set your secrets in the environment first (or source an env file):
#   export ALPACA_KEY_ID=... ALPACA_SECRET_KEY=... ANTHROPIC_API_KEY=...
# PAPER only — this script never sets ALPACA_LIVE.
set -euo pipefail

SESSION="${TRADING_AGENT_SESSION:-trading-agent}"
# repo root = two levels up from this script (agent/deploy/ -> repo)
REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
INTERVAL="${POLL_SECONDS:-60}"
BUDGET_PCT="${EVENT_BUDGET_PCT:-10}"
PY="${PYTHON:-python3}"

start() {
  command -v tmux >/dev/null || { echo "tmux not installed"; exit 1; }
  if [[ -z "${ALPACA_KEY_ID:-}" || -z "${ALPACA_SECRET_KEY:-}" ]]; then
    echo "ALPACA_KEY_ID / ALPACA_SECRET_KEY not set — would fall back to the offline paper broker."
    echo "Export them (and ANTHROPIC_API_KEY) before starting for real paper trading."
  fi
  tmux has-session -t "$SESSION" 2>/dev/null && tmux kill-session -t "$SESSION"
  # supervised restart loop: if the driver exits non-zero, wait and relaunch;
  # a clean exit (Ctrl-C / kill switch) ends the loop.
  tmux new-session -d -s "$SESSION" -c "$REPO_ROOT" \
    "while true; do \
        $PY -m agent.live_agent --interval $INTERVAL --budget-pct $BUDGET_PCT -v; \
        code=\$?; \
        [ \$code -eq 0 ] && echo '[run_tmux] clean exit — stopping' && break; \
        echo \"[run_tmux] driver exited (\$code); restarting in 10s\"; sleep 10; \
     done"
  echo "Started tmux session '$SESSION' (interval=${INTERVAL}s, budget=${BUDGET_PCT}%)."
  echo "Watch:  $0 attach     Stop: $0 stop     Kill+flatten: $0 kill"
}

case "${1:-start}" in
  start)  start ;;
  attach) tmux attach -t "$SESSION" ;;
  status) tmux has-session -t "$SESSION" 2>/dev/null && echo "running" || echo "not running" ;;
  stop)   tmux kill-session -t "$SESSION" 2>/dev/null && echo "stopped" || echo "not running" ;;
  kill)   touch "$REPO_ROOT/experiments/live/KILL"
          echo "KILL placed — the next poll flattens and halts. Remove it before restarting:"
          echo "  rm $REPO_ROOT/experiments/live/KILL" ;;
  *) echo "usage: $0 {start|attach|status|stop|kill}"; exit 1 ;;
esac
