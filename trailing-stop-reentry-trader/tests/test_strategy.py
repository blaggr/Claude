"""Sanity tests for the trailing-stop / re-entry engine.

Run with:  python -m pytest -q   (from the project root)
These use hand-built price paths so the expected fills are obvious, plus the
offline synthetic series so the test suite never needs the network.
"""
import os
import sys

import numpy as np
import pandas as pd

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from strategy import StrategyParams, StreamingStrategy, run_backtest  # noqa: E402
import data as data_mod  # noqa: E402


def _bars(closes):
    """Build a simple OHLC frame where O=H=L=C (no intrabar noise)."""
    idx = pd.date_range("2024-01-01", periods=len(closes), freq="D", name="time")
    c = np.array(closes, dtype=float)
    return pd.DataFrame({"open": c, "high": c, "low": c, "close": c,
                         "volume": np.ones(len(c))}, index=idx)


def test_trailing_stop_fires_after_peak():
    # rise to 110 then fall; $5 trail => stop at 105 -> exits when close hits 105
    df = _bars([100, 105, 110, 108, 105, 104])
    params = StrategyParams(trail=5, reentry=1, use_intrabar=False)
    res = run_backtest(df, params, initial_capital=10_000)
    closed = [t for t in res.trades if t.exit_reason == "trailing_stop"]
    assert len(closed) == 1
    assert closed[0].entry_price == 100
    assert closed[0].exit_price == 105  # peak 110 - 5 trail


def test_reentry_one_point_up():
    # exit at 105, then need to climb to 106 (exit + $1) to re-enter
    df = _bars([100, 110, 105, 105.5, 106, 107])
    params = StrategyParams(trail=5, reentry=1, use_intrabar=False)
    res = run_backtest(df, params, initial_capital=10_000)
    entries = [t.entry_price for t in res.trades]
    # first entry at 100, re-entry once close reaches >= 106
    assert entries[0] == 100
    assert any(abs(e - 106) < 1e-9 for e in entries), entries


def test_streaming_matches_rule():
    s = StreamingStrategy(StrategyParams(trail=2, reentry=1))
    assert s.update(100)["action"] == "BUY"   # initial entry
    assert s.update(105) is None               # peak rises, no exit
    ev = s.update(102.9)                        # 105 - 2 = 103 stop -> exit
    assert ev is not None and ev["action"] == "SELL"
    assert s.update(103.5) is None             # below 102.9 + 1 trigger
    assert s.update(104.0)["action"] == "BUY"  # re-entry one point up


def test_synthetic_backtest_runs():
    df = data_mod.synthetic_ohlcv(n=120, seed=1)
    res = run_backtest(df, StrategyParams(trail=1.5, reentry=1), initial_capital=10_000)
    assert len(res.equity) == len(df)
    assert res.final_equity > 0
    # summary keys present and numeric
    s = res.summary()
    for k in ("total_return_pct", "buy_hold_return_pct", "num_trades", "max_drawdown_pct"):
        assert k in s


if __name__ == "__main__":
    # allow running without pytest
    for name, fn in list(globals().items()):
        if name.startswith("test_") and callable(fn):
            fn()
            print(f"ok  {name}")
    print("all tests passed")
