"""Tests for the trailing-stop / re-entry engine.

Run with:  python -m pytest -q   (from the project root)
These use hand-built price paths so the expected fills are obvious, plus the
offline synthetic series so the test suite never needs the network. They cover
the intrabar fill model, the enter_at_start=False path, open-trade accounting,
and streaming/backtest equivalence — the behaviours the engine actually ships.
"""
import os
import sys

import numpy as np
import pandas as pd
import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from strategy import StrategyParams, StreamingStrategy, run_backtest, BacktestResult  # noqa: E402
import data as data_mod  # noqa: E402


def _bars(closes):
    """Build a simple OHLC frame where O=H=L=C (no intrabar noise)."""
    idx = pd.date_range("2024-01-01", periods=len(closes), freq="D", name="time")
    c = np.array(closes, dtype=float)
    return pd.DataFrame({"open": c, "high": c, "low": c, "close": c,
                         "volume": np.ones(len(c))}, index=idx)


def _ohlc(rows):
    """Build an OHLC frame from explicit (open, high, low, close) tuples."""
    idx = pd.date_range("2024-01-01", periods=len(rows), freq="D", name="time")
    arr = np.array(rows, dtype=float)
    return pd.DataFrame({"open": arr[:, 0], "high": arr[:, 1],
                         "low": arr[:, 2], "close": arr[:, 3],
                         "volume": np.ones(len(rows))}, index=idx)


# --------------------------------------------------------------------------
# Original sanity tests (close-only, hand-built paths)
# --------------------------------------------------------------------------
def test_trailing_stop_fires_after_peak():
    df = _bars([100, 105, 110, 108, 105, 104])
    params = StrategyParams(trail=5, reentry=1, use_intrabar=False)
    res = run_backtest(df, params, initial_capital=10_000)
    closed = [t for t in res.trades if t.exit_reason == "trailing_stop"]
    assert len(closed) == 1
    assert closed[0].entry_price == 100
    assert closed[0].exit_price == 105  # peak 110 - 5 trail


def test_reentry_one_point_up():
    df = _bars([100, 110, 105, 105.5, 106, 107])
    params = StrategyParams(trail=5, reentry=1, use_intrabar=False)
    res = run_backtest(df, params, initial_capital=10_000)
    entries = [t.entry_price for t in res.trades]
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
    s = res.summary()
    for k in ("total_return_pct", "buy_hold_return_pct", "num_trades", "max_drawdown_pct"):
        assert k in s


# --------------------------------------------------------------------------
# Intrabar fill model (use_intrabar=True) — previously untested
# --------------------------------------------------------------------------
def test_intrabar_gap_below_stop_fills_at_open():
    # enter at 100 (trail 1 -> stop 99); next bar gaps wholly below the stop.
    df = _ohlc([(100, 100, 100, 100), (90, 91, 89, 90)])
    res = run_backtest(df, StrategyParams(trail=1, use_intrabar=True), 10_000)
    closed = [t for t in res.trades if t.exit_reason == "trailing_stop"]
    assert len(closed) == 1
    assert closed[0].exit_price == 90  # filled at the gapped-down open


def test_intrabar_low_touch_fills_at_stop_level():
    # peak rises to 105 (trail 2 -> stop 103); a later bar's low pierces it.
    df = _ohlc([(100, 100, 100, 100), (101, 105, 102, 104), (104, 104, 97, 100)])
    res = run_backtest(df, StrategyParams(trail=2, use_intrabar=True), 10_000)
    closed = [t for t in res.trades if t.exit_reason == "trailing_stop"]
    assert len(closed) == 1
    assert closed[0].exit_price == 103  # filled exactly at the stop, not the low


def test_entry_bar_high_extends_peak():
    # M1: the entry bar's own high (110) must lift the peak so the stop is 109.
    # With the bug, the peak stayed at the 100 fill and bar 1 would not exit.
    df = _ohlc([(100, 110, 100, 100), (108, 108, 108, 108)])
    res = run_backtest(df, StrategyParams(trail=1, use_intrabar=True), 10_000)
    closed = [t for t in res.trades if t.exit_reason == "trailing_stop"]
    assert len(closed) == 1
    assert closed[0].exit_price == 108  # stop 109 hit at the next open


def test_reentry_and_stop_can_fire_same_bar():
    # M2: re-enter at 102 then the same bar's low (98) pierces the new stop 101.
    df = _ohlc([
        (100, 100, 100, 100),   # enter 100, peak 100, stop 99
        (100, 100, 95, 96),     # low 95 -> stop at 99, exit 99; trigger 100
        (102, 102, 98, 100),    # re-enter 102, stop 101, low 98 -> exit same bar
    ])
    res = run_backtest(df, StrategyParams(trail=1, reentry=1, use_intrabar=True), 10_000)
    same_bar = [t for t in res.trades if t.entry_price == 102]
    assert len(same_bar) == 1
    assert same_bar[0].exit_price == 101
    assert same_bar[0].bars_held == 0  # opened and stopped within one bar


# --------------------------------------------------------------------------
# enter_at_start=False (B1) — previously a permanent no-op
# --------------------------------------------------------------------------
def test_no_start_entry_buys_on_first_trigger_backtest():
    # trigger armed at the first open (100) + reentry (1) = 101.
    df = _bars([100, 100, 101, 102])
    res = run_backtest(df, StrategyParams(trail=1, reentry=1, use_intrabar=False,
                                          enter_at_start=False), 10_000)
    entries = [t.entry_price for t in res.trades]
    assert entries, "enter_at_start=False must still eventually buy"
    assert entries[0] == 101


def test_no_start_entry_buys_on_first_trigger_streaming():
    s = StreamingStrategy(StrategyParams(trail=1, reentry=1, enter_at_start=False))
    assert s.update(100) is None         # first tick only arms the trigger (101)
    assert s.update(100.5) is None       # below trigger
    ev = s.update(101)                   # reaches trigger -> buy
    assert ev is not None and ev["action"] == "BUY"


# --------------------------------------------------------------------------
# Streaming / close-only backtest equivalence (B2 / M8)
# --------------------------------------------------------------------------
def test_streaming_equals_close_only_backtest():
    closes = [100, 105, 110, 107, 108, 112, 109, 106, 111, 103, 104, 109]
    df = _bars(closes)
    params = StrategyParams(trail=2, reentry=1, use_intrabar=False)
    bt = [(t.entry_price, t.exit_price) for t in run_backtest(df, params, 10_000).trades
          if t.exit_reason == "trailing_stop"]

    s = StreamingStrategy(params)
    stream, entry = [], None
    for px in closes:
        ev = s.update(float(px))
        if not ev:
            continue
        if ev["action"] == "BUY":
            entry = ev["price"]
        else:
            stream.append((entry, ev["price"]))
    assert bt == stream


# --------------------------------------------------------------------------
# Re-entry threshold is pinned EXACTLY (old test straddled the boundary)
# --------------------------------------------------------------------------
def test_reentry_threshold_is_exact():
    s = StreamingStrategy(StrategyParams(trail=2, reentry=1))
    s.update(100); s.update(105)
    assert s.update(102.9)["action"] == "SELL"   # exit, trigger = 103.9
    assert s.update(103.89) is None              # just below the trigger
    assert s.update(103.90)["action"] == "BUY"   # exactly at the trigger


# --------------------------------------------------------------------------
# Open-trade accounting (numeric, not just "key exists")
# --------------------------------------------------------------------------
def test_open_trade_accounting():
    df = _bars([100, 101, 102])
    res = run_backtest(df, StrategyParams(trail=100, use_intrabar=False), 10_000)
    assert res.num_trades == 0           # nothing closed
    open_trades = [t for t in res.trades if t.exit_reason == "open"]
    assert len(open_trades) == 1
    t = open_trades[0]
    assert t.shares == pytest.approx(100.0)          # 10000 / 100
    assert t.pnl == pytest.approx(200.0)             # (102 - 100) * 100
    assert t.return_pct == pytest.approx(0.02)
    assert t.bars_held == 2


# --------------------------------------------------------------------------
# Benchmark uses the same entry the strategy gets (M3)
# --------------------------------------------------------------------------
def test_buy_hold_benchmarks_from_first_open():
    df = _ohlc([(100, 100, 90, 90), (101, 101, 100, 100), (102, 110, 102, 110)])
    res = run_backtest(df, StrategyParams(trail=50, use_intrabar=False), 10_000)
    # buy-and-hold should be last close (110) over the first OPEN (100), = 10%,
    # not last close over first close (90) = 22%.
    assert res.buy_hold_return == pytest.approx(0.10)


# --------------------------------------------------------------------------
# Edge cases and metric guards
# --------------------------------------------------------------------------
def test_empty_dataframe_raises():
    with pytest.raises(ValueError):
        run_backtest(_bars([]), StrategyParams())


def test_single_bar_leaves_open_trade():
    res = run_backtest(_bars([100]), StrategyParams(trail=1), 10_000)
    assert res.num_trades == 0
    assert any(t.exit_reason == "open" for t in res.trades)


def test_huge_trail_never_exits():
    res = run_backtest(_bars([100, 90, 80, 95]), StrategyParams(trail=1000), 10_000)
    assert res.num_trades == 0


def test_zero_capital_does_not_crash():
    res = run_backtest(_bars([100, 101, 102]), StrategyParams(), initial_capital=0.0)
    assert res.total_return == 0.0


def test_max_drawdown_finite_on_total_wipeout():
    res = BacktestResult(params=StrategyParams(), initial_capital=10_000.0,
                         equity=pd.Series([0.0, 0.0, 0.0]))
    assert res.max_drawdown == 0.0  # not NaN


if __name__ == "__main__":
    sys.exit(pytest.main([__file__, "-q"]))
