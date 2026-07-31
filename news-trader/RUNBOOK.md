# Runbook — reading the gate on REAL data

Phase 1 (this package) is the backtest harness. To get an actual edge verdict it
needs two real inputs: a **release calendar** (event timestamps) and **minute
bars** around those events. Bars require an Alpaca key — that is the only
credential in the loop.

> Honest expectation up front: with vintage-quality timing, pessimistic costs,
> and a strict no-look-ahead exit, the macro **drift** signal may well come out
> flat or negative out-of-sample. That "no edge" result is the harness working,
> not failing. Do not deploy anything until the gate genuinely passes.

## 1. Alpaca market-data key (paper keys are fine for data)
```bash
export ALPACA_KEY_ID=PK...      # from alpaca.markets dashboard
export ALPACA_SECRET_KEY=...
```
Free `iex` feed has limited history/coverage; `--feed sip` (paid) gives full
depth. The harness only needs intraday bars in the event windows.

## 2. Real release calendar → `sample_data/events.csv`
Columns: `ts,type,symbol` with `ts` the **exact release datetime in UTC**
(CPI/NFP are 08:30 ET = 13:30 UTC; FOMC statement 14:00 ET = 19:00 UTC; adjust
for DST). Populate from the **official published schedules** (BLS release
schedule, Federal Reserve FOMC calendar) — do NOT guess dates. One row per
historical release you want in the test, e.g.:
```
ts,type,symbol
2023-01-12T13:30:00Z,CPI,SPY
2023-02-14T13:30:00Z,CPI,SPY
...
```
(Map each release type to the instrument its surprise most cleanly drives —
CPI/NFP → a rate-sensitive ETF like TLT/IEF; keep it small and liquid.)

## 3. Fetch real minute bars for each symbol over the full window
```bash
python fetch_bars.py --symbol SPY --start 2023-01-01 --end 2024-12-31 --out sample_data/SPY.csv
# repeat per symbol you reference in events.csv
```

## 4. Read the gate (walk-forward, out-of-sample)
```python
from prices import load_bars
from macro_calendar import load_events
from costs import CostModel
from validate import walk_forward

events = load_events("sample_data/events.csv")
bars = {"SPY": load_bars("sample_data/SPY.csv")}   # add every symbol used
grid = [{"delta_s": 60, "measure_min": m, "horizon_min": h, "trail": t}
        for m in (5, 10) for h in (30, 60, 120) for t in (None, 1.0, 2.0)]
rep = walk_forward(events, bars, grid, CostModel(half_spread_bps=2, impact_bps=1),
                   train_frac=0.6, min_sharpe=0.8, max_dd=-0.25, min_n=20)
print("configs tried:", rep["n_configs"], "| train n:", rep["n_train"], "| test n:", rep["n_test"])
print("TRAIN:", rep["train"])
print("TEST :", rep["test"])
print("PASSED THE GATE:", rep["passed"])
```

## 5. Read it honestly
- `passed == True` only if, **out-of-sample**: Sharpe ≥ 0.8, max-DD ≥ −25%,
  beats buy-and-hold, and `n_trades ≥ 20`. All four, or it's a no.
- A big TRAIN vs TEST gap = overfitting from the grid sweep; distrust it.
- Small `n` = luck, not edge — the gate's `min_n` guards this.

## What this still is NOT
Signal A (surprise), the live AI consensus, and live/paper execution
(`alpaca-py` bracket orders) are later phases. This runbook only reads the
backtest verdict on the **drift** signal.
