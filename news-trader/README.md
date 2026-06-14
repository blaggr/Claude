# news-trader — Phase 1: Drift-Signal Backtest Harness

Spec: [`../docs/superpowers/specs/2026-06-13-admin-news-trading-strategy-design.md`](../docs/superpowers/specs/2026-06-13-admin-news-trading-strategy-design.md)

## What this is

A free, offline, test-driven backtest harness for the post-macro-release **drift signal (B)**.
The core question it answers: does the momentum that forms in the 10-minute window after a
macro release persist long enough to trade profitably after realistic costs?

The harness is designed to answer that rigorously:

- **Strict no-look-ahead.** The signal reads only bars inside the measurement window
  (`[release + 60 s, release + 60 s + 10 min]`). Entry is at the close of that window.
  Exit logic scans only bars that arrive after entry.
- **Pessimistic cost model.** Each trade pays a flat per-side basis-point haircut
  (`half_spread + impact`). No commission term; no size scaling.
- **Walk-forward ready.** `run_backtest` accepts any event list; you partition the data
  yourself to keep train and test sets clean.

## What it is NOT / out of scope

| Deferred | Notes |
|---|---|
| Real data fetchers | The harness ingests CSVs. ALFRED/BLS/Alpaca connectors are Phase 2. |
| Signal A (surprise) | Requires consensus estimates + LLM/NLP; not wired up yet. |
| Live / paper execution | No broker integration of any kind. |

## Honest caveat on the sample data

The sample data (`sample_data/`) is synthetic plumbing-check data — three CPI events on one
ticker (SPY), a handful of bars. A result like `trades=2  sharpe=0.10` is **not evidence of edge**.
Real edge assessment needs: genuine historical macro releases, minute bars across a large
event universe, and walk-forward validation on a held-out period. That evaluation may well
come out flat or negative after costs.

## Running

```bash
# Tests (all modules)
cd news-trader
/usr/bin/python3 -m pytest -q

# Full backtest CLI
/usr/bin/python3 run.py --events sample_data/events.csv --bars-dir sample_data
# Optional flags:
#   --horizon-min 30   exit horizon in minutes (default 30)
#   --trail 0.005      trailing stop fraction (default: none)
#   --capital 10000    starting capital (default: 10 000)
```

Output format: `trades=N  total=±X%  sharpe=Y  maxDD=±Z%  hit=P%`

## Module map

| File | Role |
|---|---|
| `macro_calendar.py` | Load and filter macro event CSV |
| `prices.py` | Load OHLCV bar CSV |
| `costs.py` | `CostModel` — commission + spread |
| `signals.py` | `drift_signal` — measurement-window momentum classifier |
| `backtest.py` | Event loop, position sizing, P&L |
| `metrics.py` | Sharpe, drawdown, hit rate |
| `validate.py` | Data-integrity checks |
| `run.py` | CLI entry point |
