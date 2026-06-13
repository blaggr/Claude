"""Offline tests for the Alpaca trailing-stop trader (broker-managed-stop design).

The FakeBroker models a SERVER-SIDE trailing-stop order: a resting sell order the
broker tracks and can "fire" (trigger_stop), removing the position. Because the
stop lives at the broker, position-read lag and transient errors are no longer
safety-critical — these tests assert that, plus the entry/stop/re-entry cycle.
"""
import os
import sys
from collections import deque

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import risk  # noqa: E402
import alpaca_trader as at  # noqa: E402
from broker import BrokerError  # noqa: E402
from alpaca_trader import AlpacaTrader  # noqa: E402

_DONE = ("filled", "canceled", "expired", "rejected", "done_for_day")


class FakeBroker:
    def __init__(self, prices, *, is_open=True, equity=10_000.0, cash=10_000.0,
                 timestamp="2024-03-01T10:00:00-05:00", slippage=0.0,
                 stop_raises=False, hide_position=0):
        self._prices = deque(prices)
        self._last = prices[0] if prices else 0.0
        self.is_open = is_open
        self.equity = equity
        self.cash = cash
        self.timestamp = timestamp
        self.slippage = slippage
        self.stop_raises = stop_raises
        self.hide_position = hide_position
        self._pos = None
        self.orders = {}                 # id -> order dict
        self._oid = 0
        self.buys = []
        self.stop_id = None
        self.flatten_calls = 0
        self.canceled = []

    # reads
    def clock(self):
        return {"is_open": self.is_open, "timestamp": self.timestamp}

    def account(self):
        return {"equity": self.equity, "cash": self.cash, "status": "ACTIVE"}

    def position(self, symbol):
        if self.hide_position > 0:
            self.hide_position -= 1
            return None
        return dict(self._pos) if self._pos else None

    def last_price(self, symbol):
        if self._prices:
            self._last = self._prices.popleft()
        return self._last

    # orders
    def buy(self, symbol, qty, *, extended_hours=False, limit_price=None, client_order_id=None):
        fp = self._last + self.slippage
        self._pos = {"qty": float(qty), "avg_entry_price": fp}
        self.buys.append((qty, fp, client_order_id))
        self.cash -= qty * fp
        return {"filled_qty": float(qty), "fill_price": fp}

    def submit_trailing_stop(self, symbol, qty, trail_price, *, client_order_id=None):
        if self.stop_raises:
            raise BrokerError("stop rejected", code=403)
        self._oid += 1
        oid = f"o{self._oid}"
        self.orders[oid] = {"id": oid, "status": "new", "filled_avg_price": None,
                            "qty": qty, "trail": trail_price}
        self.stop_id = oid
        return {"id": oid}

    def get_order(self, order_id):
        return dict(self.orders[order_id]) if order_id in self.orders else None

    def open_orders(self, symbol):
        return [dict(o) for o in self.orders.values() if o["status"] not in _DONE]

    def cancel_order(self, order_id):
        self.canceled.append(order_id)
        if order_id in self.orders and self.orders[order_id]["status"] not in _DONE:
            self.orders[order_id]["status"] = "canceled"
        if order_id == self.stop_id:
            self.stop_id = None

    def flatten_all(self):
        self.flatten_calls += 1
        self._pos = None
        if self.stop_id and self.stop_id in self.orders:
            self.orders[self.stop_id]["status"] = "canceled"
        self.stop_id = None

    # test helper: the broker fires the resting trailing stop
    def trigger_stop(self, fill_price):
        assert self.stop_id, "no resting stop to fire"
        self.orders[self.stop_id].update(status="filled", filled_avg_price=fill_price)
        self._pos = None
        self.stop_id = None


@pytest.fixture(autouse=True)
def _isolate(tmp_path, monkeypatch):
    monkeypatch.setattr(risk, "KILL_FILE", str(tmp_path / "KILL"))
    monkeypatch.setattr(at.time, "sleep", lambda s: None)


def _trader(broker, tmp_path, **kw):
    return AlpacaTrader(broker, "SPY", kw.get("trail", 2.0), kw.get("reentry", 1.0),
                        enter_at_start=kw.get("enter_at_start", True),
                        state_file=str(tmp_path / "state.json"),
                        journal_file=str(tmp_path / "journal.jsonl"))


# ---------------------------------------------------------------- entry + stop
def test_entry_places_buy_and_protective_stop(tmp_path):
    b = FakeBroker([100.0])
    t = _trader(b, tmp_path, trail=2)
    t.step()
    assert t.mode == "long"
    assert len(b.buys) == 1
    assert b.stop_id is not None                       # a resting stop was placed
    assert t.stop_order_id == b.stop_id
    assert t.entry_price == 100.0


def test_entry_flattens_if_stop_cannot_be_placed(tmp_path):
    # If the protective stop is rejected, we must NOT hold a naked position.
    b = FakeBroker([100.0], stop_raises=True)
    t = _trader(b, tmp_path, trail=2)
    t.step()
    assert t.mode == "flat"
    assert b.flatten_calls == 1
    assert b.position("SPY") is None
    assert any("entry_unprotected_flattened" in l for l in open(t.journal_file))


def test_stop_anchors_to_actual_fill(tmp_path):
    b = FakeBroker([100.0], slippage=1.5)
    t = _trader(b, tmp_path, trail=2)
    t.step()
    assert t.entry_price == pytest.approx(101.5)       # the real fill, not the tick


# ---------------------------------------------------------------- stop fires -> re-entry
def test_stop_fire_arms_reentry_off_fill_price(tmp_path):
    b = FakeBroker([100.0, 98.0])                      # post-stop price below the re-entry trigger
    t = _trader(b, tmp_path, trail=2, reentry=1)
    t.step()                                           # long, stop resting
    b.trigger_stop(97.4)                               # broker fires the stop at 97.4
    t.step()                                           # client notices via _sync; 98 < 97.4+1
    assert t.mode == "flat"
    assert t.last_exit_price == 97.4                   # the real stop fill, not the tick
    assert any("STOPPED_OUT" in l for l in open(t.journal_file))


def test_reentry_after_stop(tmp_path):
    b = FakeBroker([100.0, 98.0, 98.3, 99.5])
    t = _trader(b, tmp_path, trail=2, reentry=1)
    t.step()                                           # buy @100
    b.trigger_stop(98.0)                               # stop fires, last_exit=98, trigger=99
    t.step()                                           # 98.0 < 99 -> flat
    assert t.mode == "flat"
    t.step()                                           # 98.3 < 99 -> still flat
    assert t.mode == "flat"
    t.step()                                           # 99.5 >= 99 -> re-enter
    assert t.mode == "long"
    assert len(b.buys) == 2


def test_no_start_entry_waits_then_buys_on_trigger(tmp_path):
    b = FakeBroker([100.0, 100.5, 101.0])
    t = _trader(b, tmp_path, trail=2, reentry=1, enter_at_start=False)
    t.step()                                           # arms trigger at 100 (+1=101); no buy
    assert t.mode == "flat" and len(b.buys) == 0
    t.step()                                           # 100.5 < 101
    assert len(b.buys) == 0
    t.step()                                           # 101 >= 101 -> buy
    assert t.mode == "long" and len(b.buys) == 1


# ---------------------------------------------------------------- sync / recovery
def test_adopts_and_protects_an_unprotected_held_position(tmp_path):
    b = FakeBroker([100.0])
    b._pos = {"qty": 95.0, "avg_entry_price": 100.0}   # held, no stop (crash window)
    t = _trader(b, tmp_path, trail=2)
    t.step()
    assert t.mode == "long"
    assert b.stop_id is not None                       # a protective stop was attached
    assert any("adopt_long" in l for l in open(t.journal_file))


def test_resubmits_stop_if_it_vanishes_while_long(tmp_path):
    b = FakeBroker([100.0, 101.0])
    t = _trader(b, tmp_path, trail=2)
    t.step()                                           # long, stop resting
    old = t.stop_order_id
    b.orders[old]["status"] = "canceled"; b.stop_id = None   # stop canceled externally
    t.step()                                           # still holding -> must re-place
    assert b.stop_id is not None
    assert t.stop_order_id != old
    assert any("stop_missing_resubmit" in l for l in open(t.journal_file))


def test_transient_position_lag_while_long_does_not_flip_flat(tmp_path):
    # While LONG with the stop still resting (NOT fired), a transient empty
    # position read must NOT flip the engine flat (which could re-buy). The stop
    # is resting, so we stay long.
    b = FakeBroker([100.0, 100.0])
    t = _trader(b, tmp_path, trail=2, reentry=1)
    t.step()                                           # long, stop resting
    b.hide_position = 1                                # next position read lags empty
    t.step()
    assert t.mode == "long"                            # stayed long (stop not fired)
    assert len(b.buys) == 1                            # no re-buy


def test_503_storm_keeps_stop_resting_does_not_abandon(tmp_path):
    b = FakeBroker([100.0])
    t = _trader(b, tmp_path, trail=2)
    t.step()                                           # long, stop resting at broker
    resting = t.stop_order_id

    def boom(symbol):
        raise BrokerError("transient 503", code=503)
    b.position = boom                                  # positions endpoint down
    rc = t.run(iterations=12, poll=0)                  # > max_failures: pins "keep looping, don't bail"
    assert rc == 0                                     # survives — read failure isn't a close
    assert t.mode == "long"                            # never flipped flat
    assert b.flatten_calls == 0                        # never sold/abandoned
    assert b.orders[resting]["status"] == "new"        # protective stop still resting


# ---------------------------------------------------------------- interlocks
def test_kill_switch_cancels_stop_and_flattens(tmp_path):
    b = FakeBroker([100.0])
    t = _trader(b, tmp_path, trail=2)
    t.step()                                           # long, stop resting
    stop = t.stop_order_id
    risk.trip_kill_switch("manual")
    assert t.step() == "halt"
    assert stop in b.canceled
    assert b.flatten_calls == 1
    assert t.mode == "flat"


def test_daily_loss_halts(tmp_path):
    b = FakeBroker([100.0, 100.0])
    t = _trader(b, tmp_path)
    t.step()
    b.equity = 9_400.0
    assert t.step() == "halt"
    assert risk.kill_switch_active()


def test_total_drawdown_halts_on_slow_bleed(tmp_path):
    b = FakeBroker([100.0] * 8)
    t = _trader(b, tmp_path)
    eqs = [10_000, 9_600, 9_220, 8_850, 8_500]
    days = ["2024-03-01", "2024-03-04", "2024-03-05", "2024-03-06", "2024-03-07"]
    result = None
    for eq, day in zip(eqs, days):
        b.equity = float(eq); b.timestamp = f"{day}T10:00:00-05:00"
        result = t.step()
        if result == "halt":
            break
    assert result == "halt"
    assert any("total drawdown" in l for l in open(t.journal_file))


def test_market_closed_no_orders(tmp_path):
    b = FakeBroker([100.0], is_open=False)
    t = _trader(b, tmp_path)
    assert t.step() == "closed"
    assert b.buys == []


def test_dust_entry_skipped(tmp_path):
    b = FakeBroker([100.0], cash=50.0)
    t = _trader(b, tmp_path)
    t.step()
    assert b.buys == []
    assert t.mode == "flat"


# ---------------------------------------------------------------- persistence
def test_restart_with_resting_stop_stays_long(tmp_path):
    b = FakeBroker([100.0, 101.0])
    t1 = _trader(b, tmp_path, trail=2)
    t1.step()                                          # long, stop resting, state saved
    assert len(b.buys) == 1
    t2 = _trader(b, tmp_path, trail=2)                 # restart: reload state
    t2.step()                                          # broker still holds + stop -> stay long
    assert t2.mode == "long"
    assert len(b.buys) == 1                            # no second buy


def test_corrupt_state_recovers(tmp_path):
    sf = tmp_path / "state.json"
    sf.write_text("{ corrupt")
    b = FakeBroker([100.0])
    t = AlpacaTrader(b, "SPY", 2.0, 1.0, state_file=str(sf), journal_file=str(tmp_path / "j.jsonl"))
    assert t.mode == "flat"
    assert any("state_load_failed" in l for l in open(tmp_path / "j.jsonl"))


def test_infinity_in_state_does_not_disable_drawdown(tmp_path):
    sf = tmp_path / "state.json"
    sf.write_text('{"mode": "flat", "peak_equity": Infinity, "day_start_equity": Infinity}')
    b = FakeBroker([100.0, 100.0])
    t = AlpacaTrader(b, "SPY", 1.0, 1.0, state_file=str(sf), journal_file=str(tmp_path / "j.jsonl"))
    assert t.peak_equity is None                       # Infinity rejected
    t.step()                                           # re-seeds peak from finite equity
    b.equity = 8_000.0; b.timestamp = "2024-03-05T10:00:00-05:00"
    assert t.step() == "halt"                          # drawdown limit still fires


if __name__ == "__main__":
    sys.exit(pytest.main([__file__, "-q"]))
