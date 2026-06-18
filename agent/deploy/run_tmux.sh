#!/usr/bin/env bash
# Run the always-on agent driver in a detached tmux session that auto-restarts
# on crash. Use this when you don't have (or don't want) systemd — e.g. macOS,
# a shared box, or a quick unattended run on a VPS.
#
#   ./agent/deploy/run_tmux.sh preflight  # verify deps/keys/broker, trade nothing
#   ./agent/deploy/run_tmux.sh start      # preflight, then start (detached)
#   ./agent/deploy/run_tmux.sh attach     # watch it live (Ctrl-b d to detach)
#   ./agent/deploy/run_tmux.sh logs       # tail the log file
#   ./agent/deploy/run_tmux.sh status     # is it running?
#   ./agent/deploy/run_tmux.sh stop       # stop the driver (positions left as-is)
#   ./agent/deploy/run_tmux.sh kill       # flatten everything + stop
#
# Secrets: put them in agent/deploy/agent.env (auto-sourced) or export them
# first: ALPACA_KEY_ID, ALPACA_SECRET_KEY, ANTHROPIC_API_KEY.
# PAPER only — this script never sets ALPACA_LIVE, and preflight REFUSES to
# start if the broker would resolve to anything other than Alpaca PAPER.
set -euo pipefail

SELF="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/$(basename "${BASH_SOURCE[0]}")"
REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
SESSION="${TRADING_AGENT_SESSION:-trading-agent}"
INTERVAL="${POLL_SECONDS:-60}"
BUDGET_PCT="${EVENT_BUDGET_PCT:-10}"
PY="${PYTHON:-python3}"
LOG="${TRADING_AGENT_LOG:-$REPO_ROOT/agent/state/live_agent.log}"
MAX_RETRIES="${TRADING_AGENT_MAX_RETRIES:-10}"   # consecutive crashes before giving up

# auto-source the env file if present (keeps secrets out of the shell history)
ENV_FILE="$REPO_ROOT/agent/deploy/agent.env"
if [[ -f "$ENV_FILE" ]]; then set -a; . "$ENV_FILE"; set +a; fi

preflight() {
  local ok=1
  command -v tmux >/dev/null || { echo "FAIL: tmux not installed"; ok=0; }
  command -v "$PY" >/dev/null || { echo "FAIL: $PY not found"; ok=0; }
  "$PY" -c "import pandas" 2>/dev/null || { echo "FAIL: pandas missing (pip install pandas) — needed for the live post fetch"; ok=0; }
  if [[ -z "${ALPACA_KEY_ID:-}" || -z "${ALPACA_SECRET_KEY:-}" ]]; then
    echo "FAIL: ALPACA_KEY_ID / ALPACA_SECRET_KEY not set (would fall back to the FAKE local broker)"; ok=0
  fi
  if [[ -z "${ANTHROPIC_API_KEY:-}" ]]; then
    echo "WARN: ANTHROPIC_API_KEY not set — the offline heuristic policy will drive the loop"
  fi
  # the decisive check: the broker must resolve to Alpaca PAPER, never LIVE/local
  if [[ $ok -eq 1 ]]; then
    ( cd "$REPO_ROOT" && "$PY" - <<'PYEOF'
import sys
from agent.broker import get_broker
b = get_broker(); name = b.__class__.__name__; mode = getattr(b, "mode", "?")
print(f"broker={name} mode={mode}")
if name != "AlpacaBroker":
    print("FAIL: not connected to Alpaca (would trade a fake local account)"); sys.exit(2)
if mode != "PAPER":
    print(f"FAIL: broker mode is {mode}, refusing to start (this runner is paper-only)"); sys.exit(3)
print("OK: Alpaca PAPER")
PYEOF
    ) || ok=0
  fi
  [[ $ok -eq 1 ]] && { echo "preflight: PASS"; return 0; } || { echo "preflight: FAIL"; return 1; }
}

# the supervised loop that actually runs inside tmux: relaunch on crash with
# backoff, give up after MAX_RETRIES consecutive failures, log everything.
_supervise() {
  mkdir -p "$(dirname "$LOG")"
  local fails=0
  echo "[run_tmux $(date -u +%FT%TZ)] supervisor up (interval=${INTERVAL}s budget=${BUDGET_PCT}%)" | tee -a "$LOG"
  while true; do
    ( cd "$REPO_ROOT" && "$PY" -m agent.live_agent --interval "$INTERVAL" --budget-pct "$BUDGET_PCT" -v ) 2>&1 | tee -a "$LOG"
    code=${PIPESTATUS[0]}
    if [[ $code -eq 0 ]]; then echo "[run_tmux] clean exit — stopping" | tee -a "$LOG"; break; fi
    fails=$((fails+1))
    if [[ $fails -ge $MAX_RETRIES ]]; then
      echo "[run_tmux] $fails consecutive crashes — giving up (check $LOG)" | tee -a "$LOG"; break
    fi
    wait=$(( fails*10 )); [[ $wait -gt 120 ]] && wait=120
    echo "[run_tmux] driver exited ($code); restart $fails/$MAX_RETRIES in ${wait}s" | tee -a "$LOG"
    sleep "$wait"
  done
}

start() {
  preflight || { echo "Refusing to start — fix the FAILs above."; exit 1; }
  tmux has-session -t "$SESSION" 2>/dev/null && tmux kill-session -t "$SESSION"
  tmux new-session -d -s "$SESSION" -c "$REPO_ROOT" "$SELF _supervise"
  echo "Started tmux session '$SESSION'. Log: $LOG"
  echo "Watch: $0 attach | $0 logs    Stop: $0 stop    Kill+flatten: $0 kill"
}

case "${1:-start}" in
  preflight) preflight ;;
  _supervise) _supervise ;;            # internal: invoked inside tmux
  start)  start ;;
  attach) tmux attach -t "$SESSION" ;;
  logs)   touch "$LOG"; tail -n 50 -f "$LOG" ;;
  status) tmux has-session -t "$SESSION" 2>/dev/null && echo "running" || echo "not running" ;;
  stop)   tmux kill-session -t "$SESSION" 2>/dev/null && echo "stopped" || echo "not running" ;;
  kill)   touch "$REPO_ROOT/experiments/live/KILL"
          echo "KILL placed — the next poll flattens and halts. Remove it before restarting:"
          echo "  rm $REPO_ROOT/experiments/live/KILL" ;;
  *) echo "usage: $0 {preflight|start|attach|logs|status|stop|kill}"; exit 1 ;;
esac
