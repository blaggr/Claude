# Trailing-Stop / Re-entry Trader

A small, auditable engine for one specific trading rule, runnable on **any
stock or index fund**:

- **Enter** long (fully invested) at the start.
- **Trailing stop-loss** — track the highest price since entry (the *peak*) and
  keep a stop `trail` dollars below it. The stop only ratchets up. When price
  falls to the stop, sell.
- **Re-entry "1 point up"** — after a stop-out, buy back the moment price rises
  `reentry` dollars (default **$1.00**) above the price you were stopped out at.
  Repeat indefinitely.

All distances are in **dollars** and fully configurable. Everything here is
**backtest + paper simulation** — no real brokerage orders are ever placed.

## Install

```bash
pip install -r requirements.txt
```

`yfinance` (Yahoo Finance) supplies data for any ticker with no API key. If
your network blocks it, use a CSV or the built-in synthetic series.

## 1. Backtest (CLI)

```bash
# 2 years of SPY daily bars, $2 trail, re-enter 1 point up
python backtest.py --ticker SPY --period 2y --trail 2 --reentry 1

# offline demo on generated data (no network)
python backtest.py --synthetic --trail 1.5 --reentry 1

# your own OHLC CSV
python backtest.py --csv mydata.csv --trail 1 --reentry 1 --json
```

Reports strategy return vs. buy-and-hold, trade count, win rate, average trade,
max drawdown and time in market.

## 2. Backtest + charts (web app)

```bash
streamlit run app.py
```

Pick a ticker, set the trail and re-entry distances in the sidebar, and run.
You get a price chart with the live stop / re-entry lines and buy/sell markers,
an equity curve vs. buy-and-hold, the full metric panel, and a trade-by-trade
table. The **Live paper sim** tab gives you the exact command to leave the rule
running.

## 3. Live paper trading (simulated fills)

```bash
python paper.py --ticker SPY --trail 1.5 --reentry 1 --poll 60
```

Polls the latest price every `--poll` seconds and runs the same rule tick by
tick. Simulated BUY/SELL fills are appended to `paper_trades.csv`; engine state
is saved to `paper_state.json`, so you can stop (Ctrl-C) and resume without
losing the position. Live prices only move while the market is open.

## 4. Paper trading on Alpaca (real paper orders)

```bash
export ALPACA_KEY_ID=PK... ALPACA_SECRET_KEY=...
python alpaca_trader.py --symbol SPY --check                       # preflight
python alpaca_trader.py --symbol SPY --trail 1.5 --reentry 1 --poll 60
```

Same engine, but it places **real orders on an Alpaca paper account** and
reconciles fills/positions against the broker — the genuine "test via Alpaca"
path. Paper by default; live is locked behind explicit interlocks (kill switch,
daily loss limit, ack file). Full runbook: [`ALPACA.md`](ALPACA.md).

## How it works

| File | Role |
|------|------|
| `strategy.py` | The rule. `run_backtest` walks OHLC bars; `StreamingStrategy` processes live ticks. Shared, dollar-denominated parameters. |
| `data.py` | Data loaders: Yahoo Finance, local CSV, and an offline synthetic generator. |
| `backtest.py` | Command-line backtester. |
| `paper.py` | Live paper-trading loop off yfinance (simulated fills only). |
| `alpaca_trader.py` | Paper-trade the rule on Alpaca — real paper orders, fills reconciled, full interlocks. See [`ALPACA.md`](ALPACA.md). |
| `broker.py` / `risk.py` | Stdlib Alpaca REST adapter and the paper/live + kill-switch + daily-loss interlocks. |
| `app.py` | Streamlit dashboard. |
| `tests/test_strategy.py` | Hand-built price paths that pin down the exact fills, plus an offline run. |

### Backtest fill model

With intrabar mode on (the default), within each bar the stop is checked
against the *prior* peak using the bar's low **before** the high extends the
peak; a gap below the stop fills at the open. The entry bar is managed on the
same bar it opens (its high extends the peak, its low can stop it out), and the
re-entry and stop can both fire within one bar. This is intentionally
conservative so results aren't flattered. Pass `--close-only` for simple
close-to-close decisions.

The intrabar model is **backtest-only** — it needs each bar's high/low. The
live paper engine (`StreamingStrategy`) sees one price at a time, so it uses the
close-only rule and reproduces the `--close-only` backtest tick-for-tick. Both
paths share the same entry/exit primitives in `strategy.py`, so they can't drift
apart. With `--no-start-entry`, the re-entry trigger is armed at the first price
and the strategy buys on the first move `reentry` dollars above it.

## Important

This is a tool for **learning and validating** a strategy, not financial
advice. Backtested results do not predict future returns, and slippage,
commissions, taxes and partial fills are not modeled. Connecting the engine to
a real brokerage to trade actual money is a separate, deliberate step with real
financial risk and is **not** enabled in this project.

## Run the tests

```bash
python -m pytest -q
```
