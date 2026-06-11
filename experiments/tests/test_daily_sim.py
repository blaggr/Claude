"""Tests for the daily simulation's money math (no network).

Run:  python -m pytest experiments/tests/test_daily_sim.py -q
"""
import os
import sys

import pandas as pd

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "simulation"))
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import daily_sim as ds  # noqa: E402


def _prices(rows: dict) -> pd.DataFrame:
    """rows: {ticker: {date: (close, next_open)}} -> MultiIndex frame like yfinance."""
    frames = {}
    for t, days in rows.items():
        idx, data = [], {"Close": [], "Open": []}
        for d, (close, opn) in days.items():
            idx.append(pd.Timestamp(d))
            data["Close"].append(close)
            data["Open"].append(opn)
        frames[t] = pd.DataFrame(data, index=idx)
    return pd.concat(frames, axis=1)


def _state(pending=None, bankroll=100.0):
    return {"bankroll": bankroll, "start_bankroll": 100.0, "busted": False,
            "pending_plan": pending, "last_run": None, "days": 0, "wins": 0, "trades": 0}


def test_settle_buy_leg_profits_and_compounds():
    # BUY USO: close 70 -> open 73.5  = +5%; full weight
    pending = {"decided_on": "2026-06-10", "headline": "airstrikes!",
               "legs": [{"instrument": "USO", "side": "BUY", "weight": 1.0, "notional": 100.0,
                         "probability": 0.83, "expected_move_pct": 2.0}]}
    st = _state(pending)
    prices = _prices({"USO": {"2026-06-10": (70.0, 69.0), "2026-06-11": (71.0, 73.5)}})
    out = ds.settle(st, prices, "2026-06-11")
    assert out is not None
    assert abs(out["portfolio_ret_pct"] - 5.0) < 1e-6
    assert abs(st["bankroll"] - 105.0) < 1e-6
    assert st["trades"] == 1 and st["wins"] == 1
    assert st["pending_plan"] is None


def test_settle_sell_leg_inverts_return():
    # SELL SPY: close 600 -> open 594 = -1% move = +1% for the short
    pending = {"decided_on": "2026-06-10", "headline": "",
               "legs": [{"instrument": "SPY", "side": "SELL", "weight": 1.0, "notional": 100.0,
                         "probability": 0.83, "expected_move_pct": -0.6}]}
    st = _state(pending)
    prices = _prices({"SPY": {"2026-06-10": (600.0, 0), "2026-06-11": (590.0, 594.0)}})
    out = ds.settle(st, prices, "2026-06-11")
    assert abs(out["portfolio_ret_pct"] - 1.0) < 1e-6
    assert abs(st["bankroll"] - 101.0) < 1e-6


def test_settle_multi_leg_weights_sum():
    pending = {"decided_on": "2026-06-10", "headline": "",
               "legs": [
                   {"instrument": "USO", "side": "BUY", "weight": 0.6, "notional": 60.0,
                    "probability": 0.83, "expected_move_pct": 2.0},
                   {"instrument": "SPY", "side": "SELL", "weight": 0.4, "notional": 40.0,
                    "probability": 0.83, "expected_move_pct": -0.6}]}
    st = _state(pending)
    prices = _prices({"USO": {"2026-06-10": (100.0, 0), "2026-06-11": (0, 102.0)},   # +2% long
                      "SPY": {"2026-06-10": (600.0, 0), "2026-06-11": (0, 606.0)}})  # +1% -> -1% short
    out = ds.settle(st, prices, "2026-06-11")
    expected = 0.6 * 2.0 + 0.4 * (-1.0)   # = +0.8%
    assert abs(out["portfolio_ret_pct"] - expected) < 1e-6


def test_settle_missing_prices_keeps_plan_pending():
    pending = {"decided_on": "2026-06-10", "headline": "",
               "legs": [{"instrument": "USO", "side": "BUY", "weight": 1.0, "notional": 100.0,
                         "probability": 0.83, "expected_move_pct": 2.0}]}
    st = _state(pending)
    prices = _prices({"USO": {"2026-06-10": (70.0, 69.0)}})  # no row for today (holiday)
    assert ds.settle(st, prices, "2026-06-11") is None
    assert st["pending_plan"] is not None
    assert st["bankroll"] == 100.0


def test_build_plan_sizes_legs_to_bankroll():
    st = _state(bankroll=50.0)
    posts = [{"ts": "2026-06-11T08:00:00+00:00",
              "text": "Major AIRSTRIKES on Iran's nuclear sites tonight!"}]
    plan = ds.build_plan(st, posts, "2026-06-11", ds.nte.classify)
    assert plan is not None
    assert plan["signal"]["topic"] == "geopolitics_conflict"
    total = sum(l["notional"] for l in plan["legs"])
    assert abs(total - 50.0) < 0.1            # no leverage
    assert plan["legs"][0]["instrument"] == "USO"   # highest edge gets most weight


def test_build_plan_ignores_irrelevant_posts():
    st = _state()
    posts = [{"ts": "t", "text": "Wonderful dinner at Mar-a-Lago!"},
             {"ts": "t", "text": "Golf today was tremendous."}]
    assert ds.build_plan(st, posts, "2026-06-11", ds.nte.classify) is None


def test_bust_detection_floor():
    pending = {"decided_on": "2026-06-10", "headline": "",
               "legs": [{"instrument": "USO", "side": "BUY", "weight": 1.0, "notional": 1.5,
                         "probability": 0.83, "expected_move_pct": 2.0}]}
    st = _state(pending, bankroll=1.5)
    prices = _prices({"USO": {"2026-06-10": (100.0, 0), "2026-06-11": (0, 50.0)}})  # -50%
    ds.settle(st, prices, "2026-06-11")
    assert st["bankroll"] <= ds.BUST_FLOOR   # 0.75 <= 1.0 -> busted next check
