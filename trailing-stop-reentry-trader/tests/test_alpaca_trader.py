"""Offline tests for the Alpaca trailing-stop trader.

A FakeBroker implements the Broker protocol entirely in memory, so every order
path, interlock, and reconciliation is exercised with NO network and NO real
Alpaca account.
"""
import os
import sys
from collections import deque

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import risk  # noqa: E402
from alpaca_trader import AlpacaTrader  # noqa: E402
from strategy import StrategyParams  # noqa: E402


class FakeBroker:
    def __init__(self, prices, *, is_open=True, equity=10_000.0, cash=10_000.0,
                 timestamp="2024-03-01T10:00:00-05:00"):
        self._prices = deque(prices)
        self._last = prices[0] if prices else 0.0
        self.is_open = is_open
        self.equity = equity
        self.cash = cash
        self.timestamp = timestamp
        self._pos = None
        self.orders = []          # ("buy"/"close", qty, fill_price)
        self.flatten_calls = 0

    def clock(self):
        return {"is_open": self.is_open, "timestamp": self.timestamp}

    def account(self):
        return {"equity": self.equity, "cash": self.cash, "status": "ACTIVE"}

    def position(self, symbol):
        return dict(self._pos) if self._pos else None

    def last_price(self, symbol):
        if self._prices:
            self._last = self._prices.popleft()
        return self._last

    def buy(self, symbol, qty, *, extended_hours=False, limit_price=None,
            client_order_id=None):
        self.orders.append(("buy", qty, self._last))
        self._pos = {"qty": float(qty), "avg_entry_price": float(self._last)}
        self.cash -= qty * self._last
        return {"filled_qty": float(qty), "fill_price": float(self._last)}

    def close(self, symbol):
        if not self._pos:
            return None
        qty = self._pos["qty"]
        self.orders.append(("close", qty, self._last))
        self.cash += qty * self._last
        self._pos = None
        return {"filled_qty": qty, "fill_price": float(self._last)}

    def flatten_all(self):
        self.flatten_calls += 1
        self._pos = None


@pytest.fixture(autouse=True)
def _isolate_kill_file(tmp_path, monkeypatch):
    # Never touch the real KILL file in the package directory.
    monkeypatch.setattr(risk, "KILL_FILE", str(tmp_path / "KILL"))


def _trader(broker, tmp_path, **params):
    p = StrategyParams(trail=params.get("trail", 2.0),
                       reentry=params.get("reentry", 1.0),
                       enter_at_start=params.get("enter_at_start", True))
    return AlpacaTrader(broker, "SPY", p,
                        state_file=str(tmp_path / "state.json"),
                        journal_file=str(tmp_path / "journal.jsonl"))


def test_buy_event_places_order_and_anchors_to_fill(tmp_path):
    b = FakeBroker([100.0])
    t = _trader(b, tmp_path, trail=2)
    t.step()
    assert b.orders == [("buy", 95, 100.0)]            # floor(10000*0.95/100)
    assert b.position("SPY")["qty"] == 95
    assert t.strat.state == "long"
    assert t.strat.entry_price == 100.0 and t.strat.peak == 100.0


def test_sell_event_closes_position(tmp_path):
    b = FakeBroker([100.0, 105.0, 102.0])             # peak 105, trail 2 -> stop 103
    t = _trader(b, tmp_path, trail=2)
    t.step(); t.step(); t.step()
    assert ("close", 95, 102.0) in b.orders
    assert b.position("SPY") is None
    assert t.strat.state == "flat"
    assert t.strat.last_exit_price == 102.0


def test_kill_switch_flattens_and_halts(tmp_path):
    b = FakeBroker([100.0])
    b._pos = {"qty": 95.0, "avg_entry_price": 100.0}
    risk.trip_kill_switch("manual")
    t = _trader(b, tmp_path)
    assert t.step() == "halt"
    assert b.flatten_calls == 1
    assert b.orders == []                              # no new entries placed


def test_daily_loss_limit_flattens_and_trips_kill(tmp_path):
    b = FakeBroker([100.0], equity=10_000.0)
    t = _trader(b, tmp_path)
    t.step()                                           # day_start_equity = 10000
    b.equity = 9_400.0                                 # -6% > 5% limit
    assert t.step() == "halt"
    assert b.flatten_calls == 1
    assert risk.kill_switch_active()


def test_market_closed_places_no_orders(tmp_path):
    b = FakeBroker([100.0], is_open=False)
    t = _trader(b, tmp_path)
    assert t.step() == "closed"
    assert b.orders == []
    assert t.strat.state == "flat"


def test_dust_entry_is_skipped_and_reverts_to_flat(tmp_path):
    b = FakeBroker([100.0], cash=50.0)                 # can't afford one $100 share
    t = _trader(b, tmp_path)
    t.step()
    assert b.orders == []
    assert t.strat.state == "flat"                     # engine reverted, no fake long


def test_reconcile_adopts_an_existing_broker_position(tmp_path):
    b = FakeBroker([110.0])
    b._pos = {"qty": 95.0, "avg_entry_price": 100.0}   # broker holds, engine flat
    t = _trader(b, tmp_path, trail=2)
    t.reconcile()
    assert t.strat.state == "long"
    assert t.strat.entry_price == 100.0
    assert t.strat.peak == 100.0


def test_reconcile_goes_flat_when_position_vanished(tmp_path):
    b = FakeBroker([100.0])                             # broker flat
    t = _trader(b, tmp_path)
    t.strat.state = "long"; t.strat.entry_price = 100.0; t.strat.peak = 105.0
    t.reconcile()
    assert t.strat.state == "flat"


def test_restart_does_not_double_buy(tmp_path):
    b = FakeBroker([100.0, 101.0])
    t1 = _trader(b, tmp_path)
    t1.step()                                          # buys once, saves state
    assert len([o for o in b.orders if o[0] == "buy"]) == 1
    # New trader process, same state file + broker still holding the position.
    t2 = _trader(b, tmp_path)
    t2.step()
    assert len([o for o in b.orders if o[0] == "buy"]) == 1   # no second buy


def test_paper_mode_is_the_default(monkeypatch):
    monkeypatch.delenv("ALPACA_LIVE", raising=False)
    base_url, mode = risk.resolve_mode()
    assert mode == "PAPER"
    assert "paper" in base_url


if __name__ == "__main__":
    sys.exit(pytest.main([__file__, "-q"]))
