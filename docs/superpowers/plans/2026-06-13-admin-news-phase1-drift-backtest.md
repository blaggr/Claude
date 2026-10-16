# Admin-News Phase 1 (Drift Backtest) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** A free, offline, TDD backtest harness that answers honestly — out-of-sample, after costs — whether the post-macro-release **drift** signal (B) has edge versus buy-and-hold.

**Architecture:** A source-agnostic spine. Macro release events (timestamps only) + minute bars feed a deterministic drift classifier → an event-time fill with a pessimistic cost model → a trade ledger → risk-adjusted metrics → a walk-forward validation gate. No paid data, no LLM, no live orders in Phase 1. Strict no-look-ahead: a signal only ever sees prices at or after the release, and the trade is entered after the measurement window.

**Tech Stack:** Python 3.11, pandas, numpy, pytest. Data: local CSV fixtures for tests; ALFRED/BLS/Alpaca fetchers are out of scope for Phase 1 (the harness ingests CSVs; wiring real fetchers is a follow-on).

---

## File structure

```
news-trader/
  events.py           # Event, Signal dataclasses (the contracts)
  macro_calendar.py   # load macro release Events from a CSV (fail-loud)
  prices.py           # load minute bars; first-bar-at-or-after; fail-loud
  signals.py          # drift_signal(): deterministic, no-look-ahead
  costs.py            # CostModel: pessimistic entry/exit fills
  backtest.py         # Trade, run_backtest(): replay + exits + compounding
  metrics.py          # summarize(): total/CAGR/Sharpe/maxDD/hit/vs-B&H
  validate.py         # walk_forward() + gate()
  run.py              # CLI: run a backtest on a data dir, print the report
  requirements.txt
  README.md
  sample_data/
    events.csv        # tiny hand-built event set for tests
    SPY.csv           # tiny minute-bar fixture
  tests/
    test_events.py test_prices.py test_macro_calendar.py test_costs.py
    test_signals.py test_backtest.py test_metrics.py test_validate.py
```

---

## Task 0: Package skeleton + fixtures

**Files:**
- Create: `news-trader/requirements.txt`, `news-trader/sample_data/events.csv`, `news-trader/sample_data/SPY.csv`, `news-trader/tests/__init__.py`

- [ ] **Step 1: requirements**

```
pandas>=2.0
numpy>=1.24
pytest>=8.0
```

- [ ] **Step 2: event fixture** — `news-trader/sample_data/events.csv` (UTC timestamps; CPI 8:30 ET = 13:30 UTC)

```
ts,type,symbol
2024-01-11T13:30:00Z,CPI,SPY
2024-02-13T13:30:00Z,CPI,SPY
2024-03-12T13:30:00Z,CPI,SPY
```

- [ ] **Step 3: bar fixture** — `news-trader/sample_data/SPY.csv`. Minute bars covering each event +/- a few minutes. Build an UP-drift around 2024-01-11, a DOWN-drift around 2024-02-13, flat around 2024-03-12 (so tests can assert direction). Minimal rows per event window (release minute through release+20m). Example for the first event (repeat the pattern for the others with the stated directions):

```
ts,open,high,low,close
2024-01-11T13:30:00Z,470.00,470.10,469.90,470.00
2024-01-11T13:35:00Z,470.50,470.70,470.40,470.60
2024-01-11T13:40:00Z,471.10,471.30,471.00,471.20
2024-01-11T13:50:00Z,471.80,472.00,471.70,471.90
2024-01-11T14:05:00Z,472.40,472.60,472.30,472.50
```

- [ ] **Step 4: Commit**

```bash
git add news-trader/requirements.txt news-trader/sample_data news-trader/tests/__init__.py
git commit -m "chore: news-trader Phase 1 skeleton + sample fixtures"
```

---

## Task 1: Contracts (`events.py`)

**Files:**
- Create: `news-trader/events.py`, `news-trader/tests/test_events.py`

- [ ] **Step 1: Write the failing test**

```python
import datetime as dt
from events import Event, Signal

def test_event_is_frozen_and_tz_aware():
    e = Event(ts=dt.datetime(2024,1,11,13,30,tzinfo=dt.timezone.utc), source="macro", type="CPI")
    assert e.payload == {}
    try:
        e.ts = None  # frozen
        assert False, "Event must be immutable"
    except Exception:
        pass

def test_signal_fields():
    s = Signal(symbol="SPY", side="long", size_frac=0.5, horizon_min=120,
               trail=None, confidence=0.8, rationale="drift up")
    assert s.side == "long" and 0 < s.size_frac <= 1
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd news-trader && python -m pytest tests/test_events.py -q`
Expected: FAIL (`No module named 'events'`).

- [ ] **Step 3: Implement**

```python
"""Contracts every source, signal, and the backtest speak. Pure data."""
from __future__ import annotations
import datetime as dt
from dataclasses import dataclass, field
from typing import Optional


@dataclass(frozen=True)
class Event:
    ts: dt.datetime               # release time, tz-aware UTC
    source: str                   # e.g. "macro"
    type: str                     # e.g. "CPI" | "FOMC" | "NFP"
    payload: dict = field(default_factory=dict)


@dataclass
class Signal:
    symbol: str
    side: str                     # "long" | "short"
    size_frac: float              # fraction of capital in (0, 1]
    horizon_min: int              # holding horizon, minutes
    trail: Optional[float]        # trailing stop in $ (None = no trail)
    confidence: float
    rationale: str
    entry_ts: Optional[dt.datetime] = None   # when to enter (set by the signal; consumed by backtest)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd news-trader && python -m pytest tests/test_events.py -q`  → Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add news-trader/events.py news-trader/tests/test_events.py
git commit -m "feat: Event/Signal contracts"
```

---

## Task 2: Minute-bar loader (`prices.py`)

**Files:**
- Create: `news-trader/prices.py`, `news-trader/tests/test_prices.py`

- [ ] **Step 1: Write the failing test**

```python
import os, datetime as dt
import pytest
from prices import load_bars, first_at_or_after, PriceError

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SPY = os.path.join(HERE, "news-trader", "sample_data", "SPY.csv")

def _ts(s): return dt.datetime.fromisoformat(s)

def test_first_at_or_after_returns_first_bar_not_before():
    bars = load_bars(SPY)
    ts, px = first_at_or_after(bars, _ts("2024-01-11T13:31:00+00:00"))
    assert ts == _ts("2024-01-11T13:35:00+00:00")   # first bar >= the target
    assert px == 470.60

def test_missing_window_fails_loud():
    bars = load_bars(SPY)
    with pytest.raises(PriceError):
        first_at_or_after(bars, _ts("2099-01-01T00:00:00+00:00"))
```

- [ ] **Step 2: Run to verify fail**

Run: `cd news-trader && python -m pytest tests/test_prices.py -q` → FAIL (`No module named 'prices'`).

- [ ] **Step 3: Implement**

```python
"""Minute-bar access. Fails loud rather than silently returning bad data."""
from __future__ import annotations
import datetime as dt
import pandas as pd


class PriceError(RuntimeError):
    pass


def load_bars(path: str) -> pd.DataFrame:
    df = pd.read_csv(path)
    if "ts" not in df.columns or "close" not in df.columns:
        raise PriceError(f"{path}: bars need at least ts and close columns; got {list(df.columns)}")
    df["ts"] = pd.to_datetime(df["ts"], utc=True)
    df = df.sort_values("ts").reset_index(drop=True)
    return df


def first_at_or_after(bars: pd.DataFrame, ts: dt.datetime) -> tuple[dt.datetime, float]:
    """Return (timestamp, close) of the first bar at/after ts. Raises if none."""
    target = pd.Timestamp(ts, tz="UTC") if ts.tzinfo else pd.Timestamp(ts, tz="UTC")
    hit = bars[bars["ts"] >= target]
    if hit.empty:
        raise PriceError(f"no bar at or after {ts}")
    row = hit.iloc[0]
    return row["ts"].to_pydatetime(), float(row["close"])
```

- [ ] **Step 4: Run to verify pass**

Run: `cd news-trader && python -m pytest tests/test_prices.py -q` → PASS.

- [ ] **Step 5: Commit**

```bash
git add news-trader/prices.py news-trader/tests/test_prices.py
git commit -m "feat: fail-loud minute-bar loader"
```

---

## Task 3: Macro event source (`macro_calendar.py`)

**Files:**
- Create: `news-trader/macro_calendar.py`, `news-trader/tests/test_macro_calendar.py`

- [ ] **Step 1: Write the failing test**

```python
import os
import pytest
from macro_calendar import load_events
from events import Event

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
EV = os.path.join(HERE, "news-trader", "sample_data", "events.csv")

def test_loads_events_sorted_tz_aware():
    evs = load_events(EV)
    assert all(isinstance(e, Event) for e in evs)
    assert [e.type for e in evs] == ["CPI", "CPI", "CPI"]
    assert evs[0].ts.tzinfo is not None
    assert evs == sorted(evs, key=lambda e: e.ts)
    assert evs[0].payload["symbol"] == "SPY"

def test_bad_row_fails_loud(tmp_path):
    p = tmp_path / "bad.csv"
    p.write_text("ts,type,symbol\nnot-a-date,CPI,SPY\n")
    with pytest.raises(ValueError):
        load_events(str(p))
```

- [ ] **Step 2: Run to verify fail** — `cd news-trader && python -m pytest tests/test_macro_calendar.py -q` → FAIL.

- [ ] **Step 3: Implement**

```python
"""Phase-1 macro source: load release Events from a CSV (ts,type,symbol).

Phase 1 needs only release TIMESTAMPS (the drift signal reacts to price, not to
the actual/consensus). Wiring real BLS/Fed calendars + ALFRED actuals is a
follow-on; this ingests a curated CSV so the backtest is fully testable offline.
"""
from __future__ import annotations
import csv
import datetime as dt
from events import Event


def load_events(path: str) -> list[Event]:
    out: list[Event] = []
    with open(path) as f:
        for i, row in enumerate(csv.DictReader(f), start=2):
            try:
                ts = dt.datetime.fromisoformat(row["ts"].replace("Z", "+00:00"))
            except (KeyError, ValueError, AttributeError) as exc:
                raise ValueError(f"{path} line {i}: bad ts {row.get('ts')!r}: {exc}") from None
            if ts.tzinfo is None:
                raise ValueError(f"{path} line {i}: ts must be tz-aware")
            out.append(Event(ts=ts, source="macro", type=row["type"],
                             payload={"symbol": row["symbol"]}))
    return sorted(out, key=lambda e: e.ts)
```

- [ ] **Step 4: Run to verify pass** — PASS.

- [ ] **Step 5: Commit**

```bash
git add news-trader/macro_calendar.py news-trader/tests/test_macro_calendar.py
git commit -m "feat: macro event source (CSV, fail-loud)"
```

---

## Task 4: Cost model (`costs.py`)

**Files:**
- Create: `news-trader/costs.py`, `news-trader/tests/test_costs.py`

- [ ] **Step 1: Write the failing test**

```python
from costs import CostModel

def test_buy_pays_up_sell_receives_less():
    cm = CostModel(half_spread_bps=2.0, impact_bps=1.0)   # 3 bps each side
    assert cm.fill_buy(100.0) == 100.03
    assert cm.fill_sell(100.0) == 99.97

def test_round_trip_cost_is_positive():
    cm = CostModel()
    buy, sell = cm.fill_buy(100.0), cm.fill_sell(100.0)
    assert buy > 100.0 > sell
```

- [ ] **Step 2: Run to verify fail** → FAIL.

- [ ] **Step 3: Implement**

```python
"""Deliberately pessimistic fill model. Most 'edges' die here."""
from __future__ import annotations
from dataclasses import dataclass


@dataclass
class CostModel:
    half_spread_bps: float = 2.0     # half the bid-ask in basis points
    impact_bps: float = 1.0          # market-impact slippage

    @property
    def _edge_bps(self) -> float:
        return self.half_spread_bps + self.impact_bps

    def fill_buy(self, mid: float) -> float:
        return round(mid * (1 + self._edge_bps / 1e4), 6)

    def fill_sell(self, mid: float) -> float:
        return round(mid * (1 - self._edge_bps / 1e4), 6)
```

- [ ] **Step 4: Run to verify pass** → PASS.

- [ ] **Step 5: Commit**

```bash
git add news-trader/costs.py news-trader/tests/test_costs.py
git commit -m "feat: pessimistic cost model"
```

---

## Task 5: Drift signal (`signals.py`)

**Files:**
- Create: `news-trader/signals.py`, `news-trader/tests/test_signals.py`

The drift rule: measure the reaction over `[release+delta_s, release+delta_s+measure_min]`; enter at the END of that window in the reaction's direction. The decision uses only prices up to the entry instant — no look-ahead.

- [ ] **Step 1: Write the failing test**

```python
import os, datetime as dt
from prices import load_bars
from macro_calendar import load_events
from signals import drift_signal

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SPY = os.path.join(HERE, "news-trader", "sample_data", "SPY.csv")
EV = os.path.join(HERE, "news-trader", "sample_data", "events.csv")

def test_up_reaction_gives_long():
    bars = load_bars(SPY)
    ev = load_events(EV)[0]               # 2024-01-11, up-drift fixture
    sig = drift_signal(ev, bars, delta_s=60, measure_min=10, horizon_min=30, trail=None)
    assert sig is not None
    assert sig.side == "long"
    assert sig.symbol == "SPY"

def test_zero_reaction_returns_none():
    # build flat bars: reaction == 0 -> no trade
    import pandas as pd
    flat = pd.DataFrame({"ts": pd.to_datetime(
        ["2024-01-11T13:30Z","2024-01-11T13:31Z","2024-01-11T13:45Z"], utc=True),
        "close": [470.0, 470.0, 470.0]})
    ev = load_events(EV)[0]
    assert drift_signal(ev, flat, delta_s=60, measure_min=10, horizon_min=30, trail=None) is None
```

- [ ] **Step 2: Run to verify fail** → FAIL.

- [ ] **Step 3: Implement**

```python
"""Drift signal (B): ride the initial post-release reaction. No look-ahead —
the side is decided from the measurement window and entered at its close."""
from __future__ import annotations
import datetime as dt
from typing import Optional
import pandas as pd
from events import Event, Signal
from prices import first_at_or_after, PriceError


def drift_signal(event: Event, bars: pd.DataFrame, *, delta_s: int,
                 measure_min: int, horizon_min: int, trail: Optional[float],
                 size_frac: float = 0.95) -> Optional[Signal]:
    symbol = event.payload.get("symbol")
    start = event.ts + dt.timedelta(seconds=delta_s)
    end = start + dt.timedelta(minutes=measure_min)
    try:
        _, p0 = first_at_or_after(bars, start)
        _, p1 = first_at_or_after(bars, end)
    except PriceError:
        return None
    reaction = p1 / p0 - 1.0
    if reaction == 0:
        return None
    side = "long" if reaction > 0 else "short"
    return Signal(symbol=symbol, side=side, size_frac=size_frac,
                  horizon_min=horizon_min, trail=trail,
                  confidence=abs(reaction), rationale=f"drift {reaction:+.4%}",
                  entry_ts=end)          # enter at the measurement-window end (no look-ahead)
```

- [ ] **Step 4: Run to verify pass** → PASS.

- [ ] **Step 5: Commit**

```bash
git add news-trader/signals.py news-trader/tests/test_signals.py
git commit -m "feat: drift signal (no look-ahead)"
```

---

## Task 6: Backtest engine (`backtest.py`)

**Files:**
- Create: `news-trader/backtest.py`, `news-trader/tests/test_backtest.py`

Entry = the measurement-window close (release+delta+measure), filled through the cost model. Exit = the earlier of (entry+horizon) or a trailing stop, also cost-filled. One position at a time; bankroll compounds.

- [ ] **Step 1: Write the failing test**

```python
import os
from prices import load_bars
from macro_calendar import load_events
from signals import drift_signal
from costs import CostModel
from backtest import run_backtest

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SPY = os.path.join(HERE, "news-trader", "sample_data", "SPY.csv")
EV = os.path.join(HERE, "news-trader", "sample_data", "events.csv")

def test_backtest_produces_trades_and_costs_reduce_return():
    events = load_events(EV)
    bars = {"SPY": load_bars(SPY)}
    classify = lambda ev, b: drift_signal(ev, b, delta_s=60, measure_min=10,
                                           horizon_min=30, trail=None)
    res_free = run_backtest(events, bars, classify, CostModel(0, 0), capital=1000.0)
    res_cost = run_backtest(events, bars, classify, CostModel(5, 5), capital=1000.0)
    assert len(res_free.trades) >= 1
    # identical signals, but costs must lower the net return
    assert res_cost.final_equity <= res_free.final_equity
```

- [ ] **Step 2: Run to verify fail** → FAIL.

- [ ] **Step 3: Implement**

```python
"""Replay events into trades. One position at a time; bankroll compounds.
Strict no-look-ahead: exits scan only bars at/after entry."""
from __future__ import annotations
import datetime as dt
from dataclasses import dataclass, field
from typing import Callable, Optional
import pandas as pd
from events import Event, Signal
from prices import first_at_or_after, PriceError
from costs import CostModel


@dataclass
class Trade:
    event_ts: dt.datetime
    symbol: str
    side: str
    entry_ts: dt.datetime
    entry_px: float
    exit_ts: dt.datetime
    exit_px: float
    ret: float                      # net return on the position, after costs
    reason: str


@dataclass
class Result:
    trades: list = field(default_factory=list)
    initial_capital: float = 0.0
    final_equity: float = 0.0
    equity_curve: list = field(default_factory=list)   # (ts, equity)


def _exit(bars, entry_ts, entry_px, side, horizon_min, trail):
    """Walk bars after entry; exit at horizon or trailing stop, whichever first."""
    deadline = entry_ts + dt.timedelta(minutes=horizon_min)
    after = bars[bars["ts"] > pd.Timestamp(entry_ts, tz="UTC")]
    peak = entry_px
    for _, row in after.iterrows():
        ts, px = row["ts"].to_pydatetime(), float(row["close"])
        if trail is not None:
            if side == "long":
                peak = max(peak, px)
                if px <= peak - trail:
                    return ts, px, "trail"
            else:
                peak = min(peak, px)
                if px >= peak + trail:
                    return ts, px, "trail"
        if ts >= deadline:
            return ts, px, "horizon"
    if not after.empty:                       # ran out of data: exit at last bar
        last = after.iloc[-1]
        return last["ts"].to_pydatetime(), float(last["close"]), "eod"
    return entry_ts, entry_px, "no_exit_data"


def run_backtest(events: list[Event], bars_by_symbol: dict,
                 classify_fn: Callable[[Event, pd.DataFrame], Optional[Signal]],
                 cost_model: CostModel, capital: float = 10_000.0) -> Result:
    equity = capital
    res = Result(initial_capital=capital, equity_curve=[])
    for ev in events:
        bars = bars_by_symbol.get(ev.payload.get("symbol"))
        if bars is None:
            continue
        sig = classify_fn(ev, bars)
        if sig is None or sig.entry_ts is None:
            continue
        # The signal tells us WHEN to enter (its measurement-window end); the
        # backtest never reconstructs it, so the two can't drift apart.
        try:
            entry_ts, mid_in = first_at_or_after(bars, sig.entry_ts)
        except PriceError:
            continue
        entry_px = cost_model.fill_buy(mid_in) if sig.side == "long" else cost_model.fill_sell(mid_in)
        exit_ts, mid_out, reason = _exit(bars, entry_ts, mid_in, sig.side,
                                         sig.horizon_min, sig.trail)
        exit_px = cost_model.fill_sell(mid_out) if sig.side == "long" else cost_model.fill_buy(mid_out)
        ret = (exit_px / entry_px - 1.0) if sig.side == "long" else (entry_px / exit_px - 1.0)
        equity *= (1 + sig.size_frac * ret)
        res.trades.append(Trade(ev.ts, sig.symbol, sig.side, entry_ts, entry_px,
                                exit_ts, exit_px, ret, reason))
        res.equity_curve.append((exit_ts, equity))
    res.final_equity = equity
    return res
```

- [ ] **Step 4: Run to verify pass**

Run: `cd news-trader && python -m pytest tests/test_backtest.py -q` → PASS. (The entry time comes straight from `sig.entry_ts`, so no shared-constant coupling is needed.)

- [ ] **Step 5: Commit**

```bash
git add news-trader/backtest.py news-trader/tests/test_backtest.py
git commit -m "feat: backtest engine (event-time fills, costs, compounding)"
```

---

## Task 7: Metrics (`metrics.py`)

**Files:**
- Create: `news-trader/metrics.py`, `news-trader/tests/test_metrics.py`

- [ ] **Step 1: Write the failing test**

```python
from metrics import summarize
from backtest import Result, Trade
import datetime as dt

def _t(ret): 
    z = dt.datetime(2024,1,1,tzinfo=dt.timezone.utc)
    return Trade(z,"SPY","long",z,100,z,100*(1+ret),ret,"horizon")

def test_summary_keys_and_hit_rate():
    res = Result(trades=[_t(0.02), _t(-0.01), _t(0.03)], initial_capital=1000,
                 final_equity=1000*1.02*0.99*1.03)
    s = summarize(res)
    for k in ("total_return","sharpe","max_drawdown","hit_rate","n_trades"):
        assert k in s
    assert s["n_trades"] == 3
    assert abs(s["hit_rate"] - 2/3) < 1e-9

def test_benchmark_gives_vs_buyhold():
    res = Result(trades=[_t(0.02)], initial_capital=1000, final_equity=1020.0)
    s = summarize(res, benchmark_return=0.05)        # strategy +2% vs B&H +5%
    assert abs(s["buy_hold_return"] - 0.05) < 1e-9
    assert s["vs_buyhold"] < 0                        # underperformed B&H

def test_no_trades_is_safe():
    s = summarize(Result(trades=[], initial_capital=1000, final_equity=1000))
    assert s["n_trades"] == 0 and s["total_return"] == 0.0
```

- [ ] **Step 2: Run to verify fail** → FAIL.

- [ ] **Step 3: Implement**

```python
"""Risk-adjusted summary of a backtest Result."""
from __future__ import annotations
import math
import numpy as np
from backtest import Result


def summarize(res: Result, benchmark_return: float | None = None) -> dict:
    rets = [t.ret for t in res.trades]
    n = len(rets)
    if n == 0:
        out = {"total_return": 0.0, "sharpe": 0.0, "max_drawdown": 0.0,
               "hit_rate": 0.0, "n_trades": 0}
    else:
        total = res.final_equity / res.initial_capital - 1.0 if res.initial_capital else 0.0
        arr = np.array(rets, dtype=float)
        # per-trade Sharpe, annualized by trades/year (assume ~12 macro events/yr/type).
        sd = arr.std(ddof=1) if n > 1 else 0.0
        sharpe = float(arr.mean() / sd * math.sqrt(12)) if sd > 0 else 0.0
        eq = res.initial_capital * np.cumprod(1 + arr)     # compounding equity path
        peak = np.maximum.accumulate(eq)
        dd = float((eq / peak - 1.0).min())
        out = {"total_return": float(total), "sharpe": sharpe, "max_drawdown": dd,
               "hit_rate": float((arr > 0).mean()), "n_trades": n}
    if benchmark_return is not None:
        out["buy_hold_return"] = float(benchmark_return)
        out["vs_buyhold"] = float(out["total_return"] - benchmark_return)
    return out
```

- [ ] **Step 4: Run to verify pass** → PASS.

- [ ] **Step 5: Commit**

```bash
git add news-trader/metrics.py news-trader/tests/test_metrics.py
git commit -m "feat: risk-adjusted metrics"
```

---

## Task 8: Walk-forward validation + gate (`validate.py`)

**Files:**
- Create: `news-trader/validate.py`, `news-trader/tests/test_validate.py`

- [ ] **Step 1: Write the failing test**

```python
import os
from prices import load_bars
from macro_calendar import load_events
from costs import CostModel
from validate import walk_forward, gate

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SPY = os.path.join(HERE, "news-trader", "sample_data", "SPY.csv")
EV = os.path.join(HERE, "news-trader", "sample_data", "events.csv")

def test_walk_forward_reports_train_and_test_and_counts():
    events = load_events(EV)
    bars = {"SPY": load_bars(SPY)}
    grid = [{"delta_s":60,"measure_min":10,"horizon_min":30,"trail":None},
            {"delta_s":60,"measure_min":5,"horizon_min":60,"trail":None}]
    rep = walk_forward(events, bars, grid, CostModel(2,1), train_frac=0.66)
    assert rep["n_configs"] == 2
    assert rep["n_train"] >= 1 and rep["n_test"] >= 1
    assert "test" in rep and "sharpe" in rep["test"]

def test_gate_rejects_small_n_and_requires_beating_buyhold():
    strong = {"sharpe":2.0,"max_drawdown":-0.05,"vs_buyhold":0.10}
    assert gate(strong, n=3, min_sharpe=0.8, max_dd=-0.25, min_n=20) is False   # n too small
    assert gate(strong, n=30, min_sharpe=0.8, max_dd=-0.25, min_n=20) is True
    loses = {"sharpe":2.0,"max_drawdown":-0.05,"vs_buyhold":-0.02}
    assert gate(loses, n=30, min_sharpe=0.8, max_dd=-0.25, min_n=20) is False    # lost to B&H
```

- [ ] **Step 2: Run to verify fail** → FAIL.

- [ ] **Step 3: Implement**

```python
"""Walk-forward: tune on train, lock, evaluate on held-out test. Plus the gate.
Honesty: reports n_configs (sweep breadth) and n so a lucky in-sample peak on a
handful of events cannot masquerade as edge."""
from __future__ import annotations
from typing import Optional
from backtest import run_backtest
from signals import drift_signal
from metrics import summarize
from prices import first_at_or_after, PriceError


def _classify_factory(p):
    return lambda ev, bars: drift_signal(
        ev, bars, delta_s=p["delta_s"], measure_min=p["measure_min"],
        horizon_min=p["horizon_min"], trail=p["trail"])


def _buy_hold_return(events, bars_by_symbol) -> float | None:
    """Buy-and-hold of the window's primary symbol from the first event to the
    last available bar — the benchmark the strategy must beat."""
    if not events:
        return None
    symbol = events[0].payload.get("symbol")
    bars = bars_by_symbol.get(symbol)
    if bars is None or bars.empty:
        return None
    try:
        _, p_in = first_at_or_after(bars, events[0].ts)
    except PriceError:
        return None
    p_out = float(bars.iloc[-1]["close"])
    return p_out / p_in - 1.0


def walk_forward(events, bars, grid, cost_model, train_frac=0.6, capital=10_000.0):
    events = sorted(events, key=lambda e: e.ts)
    cut = max(1, int(len(events) * train_frac))
    train, test = events[:cut], events[cut:]
    best, best_metric = None, -1e18
    for p in grid:
        m = summarize(run_backtest(train, bars, _classify_factory(p), cost_model, capital))
        score = m["sharpe"]            # primary tuning key on TRAIN only
        if score > best_metric:
            best, best_metric = p, score
    train_m = summarize(run_backtest(train, bars, _classify_factory(best), cost_model, capital),
                        benchmark_return=_buy_hold_return(train, bars))
    test_m = summarize(run_backtest(test, bars, _classify_factory(best), cost_model, capital),
                       benchmark_return=_buy_hold_return(test, bars))
    return {"best_params": best, "train": train_m, "test": test_m,
            "n_configs": len(grid), "n_train": len(train), "n_test": len(test)}


def gate(test_metrics: dict, *, n: int, min_sharpe: float, max_dd: float,
         min_n: int) -> bool:
    """All must hold on the OUT-OF-SAMPLE window: enough events, Sharpe bar,
    drawdown within limit, and BEATS buy-and-hold."""
    return (n >= min_n
            and test_metrics.get("sharpe", 0.0) >= min_sharpe
            and test_metrics.get("max_drawdown", -1.0) >= max_dd       # max_dd is negative
            and test_metrics.get("vs_buyhold", -1.0) >= 0.0)
```

- [ ] **Step 4: Run to verify pass** → PASS.

- [ ] **Step 5: Commit**

```bash
git add news-trader/validate.py news-trader/tests/test_validate.py
git commit -m "feat: walk-forward validation + gate"
```

---

## Task 9: CLI runner (`run.py`) + README

**Files:**
- Create: `news-trader/run.py`, `news-trader/README.md`

- [ ] **Step 1: Implement the CLI**

```python
"""Run the drift backtest on a data directory and print the report.

    python run.py --events sample_data/events.csv --bars-dir sample_data
"""
from __future__ import annotations
import argparse, glob, os
from macro_calendar import load_events
from prices import load_bars
from costs import CostModel
from signals import drift_signal
from backtest import run_backtest
from metrics import summarize

DELTA_S, MEASURE_MIN = 60, 10     # fill delay + reaction-measurement window


def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--events", required=True)
    ap.add_argument("--bars-dir", required=True)
    ap.add_argument("--horizon-min", type=int, default=30)
    ap.add_argument("--trail", type=float, default=None)
    ap.add_argument("--capital", type=float, default=10_000.0)
    a = ap.parse_args(argv)
    events = load_events(a.events)
    bars = {os.path.splitext(os.path.basename(p))[0]: load_bars(p)
            for p in glob.glob(os.path.join(a.bars_dir, "*.csv"))
            if not p.endswith("events.csv")}
    classify = lambda ev, b: drift_signal(ev, b, delta_s=DELTA_S, measure_min=MEASURE_MIN,
                                           horizon_min=a.horizon_min, trail=a.trail)
    res = run_backtest(events, bars, classify, CostModel(), a.capital)
    s = summarize(res)
    print(f"trades={s['n_trades']}  total={s['total_return']:+.2%}  "
          f"sharpe={s['sharpe']:.2f}  maxDD={s['max_drawdown']:+.2%}  hit={s['hit_rate']:.0%}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
```

- [ ] **Step 2: Smoke-run it**

Run: `cd news-trader && python run.py --events sample_data/events.csv --bars-dir sample_data`
Expected: one line, `trades=` ≥ 1, numbers finite.

- [ ] **Step 3: README** — short: what Phase 1 is, the no-look-ahead + cost caveats, the honest "this may show no edge" note, and that execution/A are deferred. Run `python -m pytest -q` to test.

- [ ] **Step 4: Commit**

```bash
git add news-trader/run.py news-trader/README.md
git commit -m "feat: CLI runner + README"
```

---

## Task 10: Full suite + honest first read

- [ ] **Step 1:** `cd news-trader && python -m pytest -q` → all pass.
- [ ] **Step 2:** Run `run.py` on the fixtures; confirm the up/down/flat fixtures produce the expected long/short/no-trade and the cost model lowers net return vs zero-cost.
- [ ] **Step 3:** Write a one-paragraph note in the README stating that the sample-data result is a *plumbing* check, not evidence of edge — real edge requires real historical events + bars + walk-forward on a large n, and may well come out flat/negative.
- [ ] **Step 4: Commit.**

---

## Out of scope (explicit — do NOT build in Phase 1)
- Real data fetchers (ALFRED/BLS/Alpaca). The harness ingests CSVs; wiring fetchers is a follow-on.
- Signal A (surprise) and any consensus/LLM data.
- Live or paper execution / alpaca-py / bracket orders.
