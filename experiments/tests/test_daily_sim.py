"""Tests for the daily simulation's money math (no network).

Covers the event-time pipeline (build_event / scan_and_trade) and the legacy
close->open settle kept for transition. 2026-06-10 is a Wednesday (EDT, UTC-4).

Run:  python -m pytest experiments/tests/test_daily_sim.py -q
"""
import datetime as dt
import os
import sys

import pandas as pd

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "simulation"))
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import daily_sim as ds  # noqa: E402

NY = "America/New_York"
NOW = dt.datetime(2026, 6, 10, 15, 0, tzinfo=dt.timezone.utc)   # 11:00 NY


def _state(**kw):
    st = dict(ds.DEFAULT_STATE)
    st["open_events"] = []
    st["processed_ids"] = []
    st.update(kw)
    return st


def _bars(start: str, prices: list[float]) -> pd.Series:
    idx = pd.date_range(start, periods=len(prices), freq="1min", tz=NY)
    return pd.Series(prices, index=idx)


def _conflict_bars(uso_after: float):
    """Pre-market 09:00-09:29 flat, then 09:30 (the boundary bar) per ticker."""
    flat = lambda v0, v1: _bars("2026-06-10 09:00", [v0] * 30 + [v1] * 10)
    return {"USO": flat(100.0, uso_after), "GLD": flat(200.0, 200.5),
            "ITA": flat(150.0, 150.0), "SPY": flat(600.0, 597.0)}


# ---- build_event ------------------------------------------------------------

def test_build_event_maps_airstrike_post_to_conflict_legs():
    post = {"id": "p1", "ts": "2026-06-10T13:00:00+00:00",
            "text": "Major AIRSTRIKES on Iran's nuclear sites tonight!"}
    ev = ds.build_event(post, ds.nte.classify)
    assert ev is not None
    assert ev["signal"]["topic"] == "geopolitics_conflict"
    legs = {l["instrument"]: l for l in ev["legs"]}
    assert legs["USO"]["side"] == "BUY" and legs["SPY"]["side"] == "SELL"
    assert abs(sum(l["weight"] for l in ev["legs"]) - 1.0) < 0.01
    assert all(0.003 <= l["trail_pct"] <= 0.015 for l in ev["legs"])


def test_build_event_returns_none_for_irrelevant_post():
    post = {"id": "p0", "ts": "2026-06-10T13:00:00+00:00",
            "text": "Wonderful dinner at Mar-a-Lago!"}
    assert ds.build_event(post, ds.nte.classify) is None


# ---- scan_and_trade ---------------------------------------------------------

def test_event_settles_at_event_time_and_compounds():
    # post 13:00 UTC = 09:00 NY (pre-market); entry 09:05, boundary exit 09:30
    st = _state()
    posts = [{"id": "p1", "ts": "2026-06-10T13:00:00+00:00",
              "text": "Major AIRSTRIKES on Iran tonight!"}]
    out = ds.scan_and_trade(st, posts, _conflict_bars(uso_after=103.0), ds.nte.classify, NOW)
    assert len(out["settled"]) == 1
    ev = out["settled"][0]
    assert all(l["reason"] == "boundary" for l in ev["legs"])
    # USO +3% long, GLD +0.25%, ITA 0%, SPY -0.5% short => +0.5%; all weights >0
    assert ev["portfolio_ret_pct"] > 0
    assert st["bankroll"] > 100.0
    assert st["trades"] == 1 and st["wins"] == 1
    assert "p1" in st["processed_ids"]


def test_second_post_skipped_while_position_window_overlaps():
    st = _state()
    posts = [{"id": "p1", "ts": "2026-06-10T13:00:00+00:00",
              "text": "Major AIRSTRIKES on Iran tonight!"},
             {"id": "p2", "ts": "2026-06-10T13:10:00+00:00",
              "text": "More missiles launched at Iran!"}]
    out = ds.scan_and_trade(st, posts, _conflict_bars(103.0), ds.nte.classify, NOW)
    assert len(out["settled"]) == 1
    assert out["skipped"] == 1
    assert "p2" in st["processed_ids"]


def test_unresolved_event_carries_and_blocks_newer_posts():
    # bars end at 09:20 — before the 09:30 boundary -> event stays open
    flat = lambda v: _bars("2026-06-10 09:00", [v] * 20)
    bars = {t: flat(100.0) for t in ["USO", "GLD", "ITA", "SPY"]}
    st = _state()
    posts = [{"id": "p1", "ts": "2026-06-10T13:00:00+00:00",
              "text": "Major AIRSTRIKES on Iran tonight!"},
             {"id": "p2", "ts": "2026-06-10T13:10:00+00:00",
              "text": "More missiles launched at Iran!"}]
    out = ds.scan_and_trade(st, posts, bars, ds.nte.classify, NOW)
    assert out["still_open"] == 1
    assert len(st["open_events"]) == 1
    assert st["bankroll"] == 100.0
    # p2 was NOT consumed — reconsidered next run
    assert "p2" not in st["processed_ids"]


def test_carried_event_resolves_next_run():
    st = _state()
    posts = [{"id": "p1", "ts": "2026-06-10T13:00:00+00:00",
              "text": "Major AIRSTRIKES on Iran tonight!"}]
    short = {t: _bars("2026-06-10 09:00", [100.0] * 20) for t in ["USO", "GLD", "ITA", "SPY"]}
    ds.scan_and_trade(st, posts, short, ds.nte.classify, NOW)
    assert st["open_events"]
    # next run sees the full window
    out = ds.scan_and_trade(st, [], _conflict_bars(103.0), ds.nte.classify, NOW)
    assert len(out["settled"]) == 1
    assert not st["open_events"]
    assert st["bankroll"] > 100.0


def test_irrelevant_posts_marked_processed_without_trading():
    st = _state()
    posts = [{"id": "px", "ts": "2026-06-10T13:00:00+00:00", "text": "Golf was tremendous."}]
    out = ds.scan_and_trade(st, posts, {}, ds.nte.classify, NOW)
    assert not out["settled"] and not st["open_events"]
    assert "px" in st["processed_ids"]
    assert st["bankroll"] == 100.0


def test_bust_floor_halts_new_trading():
    # crash USO -50% on the boundary with an all-in long-ish book
    st = _state(bankroll=1.8)
    posts = [{"id": "p1", "ts": "2026-06-10T13:00:00+00:00",
              "text": "Major AIRSTRIKES on Iran tonight!"}]
    bars = _conflict_bars(uso_after=1.0)   # USO 100 -> 1: catastrophic long
    ds.scan_and_trade(st, posts, bars, ds.nte.classify, NOW)
    assert st["bankroll"] <= ds.BUST_FLOOR
    assert st["busted"]


# ---- legacy close->open settle (transition path) ---------------------------

def _prices(rows: dict) -> pd.DataFrame:
    frames = {}
    for t, days in rows.items():
        idx, data = [], {"Close": [], "Open": []}
        for d, (close, opn) in days.items():
            idx.append(pd.Timestamp(d))
            data["Close"].append(close)
            data["Open"].append(opn)
        frames[t] = pd.DataFrame(data, index=idx)
    return pd.concat(frames, axis=1)


def test_legacy_settle_buy_leg_profits_and_compounds():
    pending = {"decided_on": "2026-06-10", "headline": "airstrikes!",
               "legs": [{"instrument": "USO", "side": "BUY", "weight": 1.0, "notional": 100.0,
                         "probability": 0.83, "expected_move_pct": 2.0}]}
    st = _state(pending_plan=pending)
    prices = _prices({"USO": {"2026-06-10": (70.0, 69.0), "2026-06-11": (71.0, 73.5)}})
    out = ds.settle(st, prices, "2026-06-11")
    assert abs(out["portfolio_ret_pct"] - 5.0) < 1e-6
    assert abs(st["bankroll"] - 105.0) < 1e-6
    assert st["pending_plan"] is None


def test_legacy_settle_missing_prices_keeps_plan_pending():
    pending = {"decided_on": "2026-06-10", "headline": "",
               "legs": [{"instrument": "USO", "side": "BUY", "weight": 1.0, "notional": 100.0,
                         "probability": 0.83, "expected_move_pct": 2.0}]}
    st = _state(pending_plan=pending)
    prices = _prices({"USO": {"2026-06-10": (70.0, 69.0)}})
    assert ds.settle(st, prices, "2026-06-11") is None
    assert st["pending_plan"] is not None
    assert st["bankroll"] == 100.0
