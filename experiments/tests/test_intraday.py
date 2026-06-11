"""Tests for the event-time intraday fill model (no network).

Run:  python -m pytest experiments/tests/test_intraday.py -q
2026-06-10 is a Wednesday; June = EDT (UTC-4).
"""
import os
import sys

import pandas as pd

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "simulation"))

import intraday  # noqa: E402

NY = intraday.NY


def bars(start: str, prices: list[float]) -> pd.Series:
    idx = pd.date_range(start, periods=len(prices), freq="1min", tz=NY)
    return pd.Series(prices, index=idx)


def ts(s: str) -> pd.Timestamp:
    return pd.Timestamp(s, tz=NY)


def test_premarket_entry_exits_at_the_open_boundary():
    # post 07:50 -> t0 07:55 -> entry first bar (08:00); boundary = 09:30
    prices = [100.0] * 90 + [102.0] * 5          # 08:00..09:29 flat, 09:30+ at 102
    b = bars("2026-06-10 08:00", prices)
    r = intraday.simulate_leg(b, ts("2026-06-10 07:50"), "BUY", trail_pct=0.05)
    assert r["status"] == "closed"
    assert r["reason"] == "boundary"
    assert "09:30" in r["exit_ts"]
    assert abs(r["ret"] - 0.02) < 1e-9            # 100 -> 102

    r = intraday.simulate_leg(b, ts("2026-06-10 07:50"), "SELL", trail_pct=0.05)
    assert abs(r["ret"] + 0.02) < 1e-9            # short loses the same move


def test_trailing_stop_exits_long_on_reversal_before_boundary():
    # RTH: entry 100, run to 105, then fall through 105*(1-2%)=102.9
    prices = [100, 101, 102, 103, 104, 105, 104, 103, 102.5, 102.5, 102.5]
    b = bars("2026-06-10 10:05", prices)
    r = intraday.simulate_leg(b, ts("2026-06-10 10:00"), "BUY", trail_pct=0.02)
    assert r["status"] == "closed" and r["reason"] == "trailing_stop"
    assert abs(r["ret"] - 0.025) < 1e-9           # exit at 102.5


def test_trailing_stop_short_side():
    # short entry 100, fall to 95 (best), bounce to >= 95*1.02=96.9 -> exit
    prices = [100, 98, 96, 95, 96, 97]
    b = bars("2026-06-10 10:05", prices)
    r = intraday.simulate_leg(b, ts("2026-06-10 10:00"), "SELL", trail_pct=0.02)
    assert r["reason"] == "trailing_stop"
    assert abs(r["ret"] - 0.03) < 1e-9            # -1 * (97/100 - 1)


def test_rth_entry_hard_exit_by_session_close():
    # flat prices all day: no trailing exit; boundary at 15:55
    idx = pd.date_range("2026-06-10 10:05", "2026-06-10 15:59", freq="1min", tz=NY)
    b = pd.Series(100.0, index=idx)
    r = intraday.simulate_leg(b, ts("2026-06-10 10:00"), "BUY", trail_pct=0.02)
    assert r["status"] == "closed" and r["reason"] == "boundary"
    assert "15:55" in r["exit_ts"]


def test_missed_when_venue_closed_until_the_boundary():
    # 3am post, no pre-market bars: first tradable bar 09:30 == boundary
    prices = [100.0] * 30
    b = bars("2026-06-10 09:30", prices)
    r = intraday.simulate_leg(b, ts("2026-06-10 03:00"), "BUY", trail_pct=0.02)
    assert r["status"] == "missed"


def test_post_market_post_boundary_is_next_session_open():
    # 18:00 Wed post -> boundary Thu 09:30; post-market bars exist
    pm = bars("2026-06-10 18:05", [100.0] * 60)                      # Wed evening
    thu = bars("2026-06-11 09:30", [103.0] * 5)                      # Thu open
    b = pd.concat([pm, thu])
    r = intraday.simulate_leg(b, ts("2026-06-10 18:00"), "BUY", trail_pct=0.05)
    assert r["reason"] == "boundary"
    assert r["exit_ts"].startswith("2026-06-11 09:30")
    assert abs(r["ret"] - 0.03) < 1e-9


def test_open_until_data_arrives_then_stale_force_close():
    # bars end before the boundary -> open; force_close settles at last bar
    prices = [100, 101, 101.5]
    b = bars("2026-06-10 11:05", prices)
    post = ts("2026-06-10 11:00")
    assert intraday.simulate_leg(b, post, "BUY", trail_pct=0.05)["status"] == "open"
    r = intraday.simulate_leg(b, post, "BUY", trail_pct=0.05, force_close=True)
    assert r["status"] == "closed" and r["reason"] == "stale_close"
    assert abs(r["ret"] - 0.015) < 1e-9


def test_open_when_post_is_newer_than_all_bars():
    b = bars("2026-06-10 09:30", [100.0] * 10)
    r = intraday.simulate_leg(b, ts("2026-06-10 12:00"), "BUY", trail_pct=0.02)
    assert r["status"] == "open"


def test_trail_pct_clamps():
    assert abs(intraday.trail_pct_for(2.0) - 0.008) < 1e-12
    assert intraday.trail_pct_for(0.3) == 0.003     # floor
    assert intraday.trail_pct_for(6.0) == 0.015     # cap
