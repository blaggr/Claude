"""Offline tests for the Alpaca trailing-stop trader.

The FakeBroker models the behaviours real Alpaca exhibits that earlier broke the
trader: slippage (fill price != polled price), partial fills, order rejection,
and a close that fails or finds nothing. These tests are written to FAIL if the
fill-reconciliation logic regresses (see the mutation list in the review).
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
from strategy import StrategyParams  # noqa: E402


class FakeBroker:
    """In-memory broker that can slip, partially fill, reject, and fail to close."""

    def __init__(self, prices, *, is_open=True, equity=10_000.0, cash=10_000.0,
                 timestamp="2024-03-01T10:00:00-05:00",
                 slippage=0.0, fill_ratio=1.0, reject_buy=False,
                 close_raises=False, close_partial=False, reject_dupe_coid=False):
        self._prices = deque(prices)
        self._last = prices[0] if prices else 0.0
        self.is_open = is_open
        self.equity = equity
        self.cash = cash
        self.timestamp = timestamp
        self.slippage = slippage
        self.fill_ratio = fill_ratio
        self.reject_buy = reject_buy
        self.close_raises = close_raises
        self.close_partial = close_partial
        self.reject_dupe_coid = reject_dupe_coid
        self._pos = None
        self.hide_position = 0          # >0: next N position() reads return None (endpoint lag)
        self.position_script = None     # optional deque of None|"ERR"|dict for exact sequences
        self.orders = []
        self.coids = []
        self.flatten_calls = 0

    def clock(self):
        return {"is_open": self.is_open, "timestamp": self.timestamp}

    def account(self):
        return {"equity": self.equity, "cash": self.cash, "status": "ACTIVE"}

    def position(self, symbol):
        if self.position_script:                 # scripted sequence: None | "ERR" | dict
            item = self.position_script.popleft()
            if item == "ERR":
                raise BrokerError("transient 503", code=503)
            return item
        if self.hide_position > 0:
            self.hide_position -= 1
            return None
        return dict(self._pos) if self._pos else None

    def last_price(self, symbol):
        if self._prices:
            self._last = self._prices.popleft()
        return self._last

    def buy(self, symbol, qty, *, extended_hours=False, limit_price=None, client_order_id=None):
        if client_order_id is not None:
            if self.reject_dupe_coid and client_order_id in self.coids:
                raise BrokerError("client_order_id must be unique", code=422)
            self.coids.append(client_order_id)   # order is submitted regardless of fill
        if self.reject_buy:
            raise BrokerError("buy rejected: insufficient buying power", code=403)
        filled = int(qty * self.fill_ratio)
        if filled < 1:
            return None
        fp = self._last + self.slippage
        self._pos = {"qty": float(filled), "avg_entry_price": fp}
        self.cash -= filled * fp
        self.orders.append(("buy", filled, fp))
        return {"filled_qty": float(filled), "fill_price": fp}

    def close(self, symbol):
        if self.close_raises:
            raise BrokerError("could not liquidate", code=500)
        if not self._pos:
            return None
        fp = self._last + self.slippage
        if self.close_partial:
            self._pos["qty"] = self._pos["qty"] / 2.0   # leave half on the table
            return {"filled_qty": self._pos["qty"], "fill_price": fp}
        qty = self._pos["qty"]
        self._pos = None
        self.orders.append(("close", qty, fp))
        return {"filled_qty": qty, "fill_price": fp}

    def flatten_all(self):
        self.flatten_calls += 1
        self._pos = None


@pytest.fixture(autouse=True)
def _isolate_kill_file(tmp_path, monkeypatch):
    monkeypatch.setattr(risk, "KILL_FILE", str(tmp_path / "KILL"))
    monkeypatch.setattr(at.time, "sleep", lambda s: None)   # make position retries instant


def _trader(broker, tmp_path, **params):
    p = StrategyParams(trail=params.get("trail", 2.0),
                       reentry=params.get("reentry", 1.0),
                       enter_at_start=params.get("enter_at_start", True))
    return AlpacaTrader(broker, "SPY", p,
                        state_file=str(tmp_path / "state.json"),
                        journal_file=str(tmp_path / "journal.jsonl"))


# ---------------------------------------------------------------- basics
def test_buy_event_places_order(tmp_path):
    b = FakeBroker([100.0])
    t = _trader(b, tmp_path, trail=2)
    t.step()
    assert b.orders == [("buy", 95, 100.0)]
    assert t.strat.state == "long"


def test_sell_event_closes_position(tmp_path):
    b = FakeBroker([100.0, 105.0, 102.0])
    t = _trader(b, tmp_path, trail=2)
    t.step(); t.step(); t.step()
    assert any(o[0] == "close" for o in b.orders)
    assert b.position("SPY") is None
    assert t.strat.state == "flat"


# ---------------------------------------------------------------- FILL FIDELITY (these bite)
def test_stop_anchors_to_actual_fill_not_polled_price(tmp_path):
    # Real fill is 1.50 above the polled tick (slippage). The trailing stop MUST
    # anchor to the fill, not the tick. (Kills the "anchor to price" mutant.)
    b = FakeBroker([100.0], slippage=1.5)
    t = _trader(b, tmp_path, trail=2)
    t.step()
    assert t.strat.entry_price == pytest.approx(101.5)
    assert t.strat.peak == pytest.approx(101.5)


def test_partial_buy_fill_keeps_engine_long_anchored_to_fill(tmp_path):
    # Only half the order fills. The engine must hold a long anchored to the fill,
    # NOT revert to flat and orphan the shares. (Kills the no-fill-guard mutant.)
    b = FakeBroker([100.0], slippage=0.5, fill_ratio=0.5)
    t = _trader(b, tmp_path, trail=2)
    t.step()
    assert t.strat.state == "long"
    assert t.strat.entry_price == pytest.approx(100.5)
    assert b.position("SPY")["qty"] == 47   # floor(95 * 0.5)


def test_zero_fill_rolls_back_to_flat(tmp_path):
    b = FakeBroker([100.0], fill_ratio=0.0)   # nothing fills
    t = _trader(b, tmp_path, trail=2)
    t.step()
    assert t.strat.state == "flat"            # rolled back, no phantom long
    assert b.position("SPY") is None


def test_buy_rejection_rolls_back_to_flat(tmp_path):
    b = FakeBroker([100.0], reject_buy=True)
    t = _trader(b, tmp_path, trail=2)
    t.step()
    assert t.strat.state == "flat"
    assert b.orders == []
    assert any("buy_rejected" in line for line in open(t.journal_file))


def test_failed_close_keeps_engine_long(tmp_path):
    # Stop triggers but the close ERRORS. The engine must NOT lie flat; it stays
    # long so the next loop retries. (Kills the close-rejection-desync mutant.)
    b = FakeBroker([100.0, 105.0, 102.0], close_raises=True)
    t = _trader(b, tmp_path, trail=2)
    t.step(); t.step(); t.step()
    assert t.strat.state == "long"
    assert b.position("SPY") is not None


def test_partial_close_keeps_engine_long(tmp_path):
    b = FakeBroker([100.0, 105.0, 102.0], close_partial=True)
    t = _trader(b, tmp_path, trail=2)
    t.step(); t.step(); t.step()
    assert t.strat.state == "long"            # still holding the remainder
    assert b.position("SPY")["qty"] > 0


def test_reentry_baseline_uses_actual_close_fill(tmp_path):
    # SELL fills 0.40 below the tick; the re-entry baseline must be the fill, not
    # the tick. (Kills the "exit_px = price" mutant.)
    b = FakeBroker([100.0, 105.0, 102.0], slippage=-0.4)
    t = _trader(b, tmp_path, trail=2, reentry=1)
    t.step(); t.step(); t.step()
    assert t.strat.state == "flat"
    assert t.strat.last_exit_price == pytest.approx(101.6)   # 102.0 + (-0.4)


def test_vanished_position_is_reconciled_without_a_phantom_sale(tmp_path):
    # Position closed externally. reconcile() catches it (after confirmation)
    # before the sell path, so the engine goes flat with NO fabricated SELL.
    b = FakeBroker([100.0, 105.0, 102.0, 102.0])
    t = _trader(b, tmp_path, trail=2)
    t.step(); t.step()                         # long, peak 105
    b._pos = None                              # externally closed
    assert t.step() == "wait"                  # 1st empty read: do not act
    t.step()                                   # 2nd empty read: confirmed flat
    assert t.strat.state == "flat"
    events = [l for l in open(t.journal_file)]
    assert any("reconcile_flat" in l for l in events)
    assert not any('"event": "SELL"' in l for l in events)
    assert b.orders == [("buy", 95, 100.0)]    # only the entry; no close order issued


def test_transient_empty_position_does_not_double_buy(tmp_path):
    # The positions endpoint lags right after a fill. A single empty read while
    # long must NOT trigger a second all-in BUY on top of the held position.
    b = FakeBroker([100.0, 100.0, 102.0])
    t = _trader(b, tmp_path, trail=2, reentry=1)
    t.step()                                   # buy 95 @100, broker holds 95
    b.hide_position = 1                         # next read transiently empty (lag)
    assert t.step() == "wait"                  # must wait, not re-buy
    assert len([o for o in b.orders if o[0] == "buy"]) == 1
    assert b.position("SPY")["qty"] == 95      # still the original single position


# ---------------------------------------------------------------- reconcile / safety
def test_unmanaged_position_halts_and_is_left_untouched(tmp_path):
    b = FakeBroker([100.0])
    b._pos = {"qty": 500.0, "avg_entry_price": 50.0}   # a position WE did not open
    t = _trader(b, tmp_path)                            # intended_long defaults False
    assert t.step() == "halt"
    assert b.orders == []
    assert b.position("SPY")["qty"] == 500.0           # not adopted, not liquidated
    assert b.flatten_calls == 0


def test_adopts_our_own_crash_window_position(tmp_path):
    b = FakeBroker([110.0])
    b._pos = {"qty": 95.0, "avg_entry_price": 100.0}
    t = _trader(b, tmp_path, trail=2)
    t.intended_long = True                             # we DID intend this buy
    t.pending_qty = 95.0                               # and the size matches what we ordered
    assert t.reconcile(110.0) == "ok"
    assert t.strat.state == "long"
    assert t.strat.entry_price == 100.0


def test_reconcile_flat_arms_reentry_from_current_price_not_entry(tmp_path):
    b = FakeBroker([130.0])
    t = _trader(b, tmp_path, reentry=1)
    t.strat.state = "long"; t.strat.entry_price = 100.0; t.strat.peak = 130.0
    t.intended_long = True
    t.pending_qty = 95.0                               # nonzero so the clear actually bites
    b._pos = None
    assert t.reconcile(130.0) == "wait"                # 1st empty read: unconfirmed
    assert t.reconcile(130.0) == "ok"                  # 2nd: confirmed flat
    assert t.strat.state == "flat"
    assert t.strat.last_exit_price == 130.0            # not the stale entry 100
    assert t.pending_qty == 0.0                        # cleared on confirmed flat


# ---------------------------------------------------------------- interlocks
def test_kill_switch_flattens_and_halts(tmp_path):
    b = FakeBroker([100.0]); b._pos = {"qty": 95.0, "avg_entry_price": 100.0}
    risk.trip_kill_switch("manual")
    t = _trader(b, tmp_path)
    assert t.step() == "halt"
    assert b.flatten_calls == 1
    assert b.orders == []


def test_daily_loss_limit_flattens_and_trips_kill(tmp_path):
    b = FakeBroker([100.0])
    t = _trader(b, tmp_path)
    t.step()
    b.equity = 9_400.0
    assert t.step() == "halt"
    assert b.flatten_calls == 1
    assert risk.kill_switch_active()


def test_daily_loss_baseline_carries_across_overnight_gap(tmp_path):
    # Buy day 1 (baseline 10000), then a new session opens 30% lower. The carried
    # baseline must flag the gap; it must NOT re-anchor to the crashed equity.
    b = FakeBroker([100.0, 100.0])
    t = _trader(b, tmp_path)
    t.step()                                            # day 1: baseline 10000
    b.equity = 7_000.0
    b.timestamp = "2024-03-02T09:35:00-05:00"           # new session, -30%
    assert t.step() == "halt"
    assert b.flatten_calls == 1
    assert risk.kill_switch_active()


def test_market_closed_places_no_orders(tmp_path):
    b = FakeBroker([100.0], is_open=False)
    t = _trader(b, tmp_path)
    assert t.step() == "closed"
    assert b.orders == []


def test_dust_entry_is_skipped(tmp_path):
    b = FakeBroker([100.0], cash=50.0)
    t = _trader(b, tmp_path)
    t.step()
    assert b.orders == []
    assert t.strat.state == "flat"


# ---------------------------------------------------------------- persistence
def test_pending_qty_tracks_actual_filled_not_requested(tmp_path):
    # Partial fill: pending_qty must reflect what the BROKER holds (47), not the
    # 95 we requested — otherwise a restart reconcile rejects our own position.
    b = FakeBroker([100.0], fill_ratio=0.5)
    t = _trader(b, tmp_path, trail=2)
    t.step()
    assert t.strat.state == "long"
    assert t.pending_qty == 47.0                       # floor(95*0.5), the real position
    assert t._qty_matches(b.position("SPY")["qty"]) is True


def test_flatten_unconfirmed_keeps_engine_long(tmp_path):
    # flatten_all is best-effort; if the position is still held afterwards the
    # engine must NOT persist flat (which would abandon a stop-less position).
    b = FakeBroker([100.0])
    t = _trader(b, tmp_path, trail=2)
    t.step()                                            # long, broker holds 95
    b.flatten_all = lambda: None                        # flatten fails silently
    t._flatten_and_halt("kill")
    assert t.strat.state == "long"                      # not lied flat
    assert any("halt_flatten_unconfirmed" in l for l in open(t.journal_file))


def test_infinity_in_state_does_not_disable_the_drawdown_limit(tmp_path):
    # A hand-edited state with Infinity must not poison the limits. Prove the
    # drawdown limit still FIRES after loading such a state (not just that the
    # field is None) by driving a real breach.
    sf = tmp_path / "state.json"
    sf.write_text('{"strat": {"params": {"trail": 1.0, "reentry": 1.0, '
                  '"enter_at_start": true}, "state": "flat", "peak": null, '
                  '"entry_price": null, "last_exit_price": null}, '
                  '"peak_equity": Infinity, "day_start_equity": Infinity}')
    b = FakeBroker([100.0, 100.0])
    t = AlpacaTrader(b, "SPY", StrategyParams(trail=1), state_file=str(sf),
                     journal_file=str(tmp_path / "j.jsonl"))
    assert t.peak_equity is None                        # Infinity rejected on load
    t.step()                                            # peak re-seeds from finite equity 10000
    b.equity = 8_000.0                                  # -20% from the real peak
    b.timestamp = "2024-03-05T10:00:00-05:00"
    assert t.step() == "halt"                           # drawdown limit fires (not disabled)
    assert risk.kill_switch_active()


def test_load_bad_order_seq_keeps_safe_default(tmp_path):
    # A malformed field must not half-load a LONG strategy with wiped baselines.
    sf = tmp_path / "state.json"
    sf.write_text('{"strat": {"params": {"trail": 2.0, "reentry": 1.0, '
                  '"enter_at_start": true}, "state": "long", "peak": 105.0, '
                  '"entry_price": 100.0, "last_exit_price": null}, '
                  '"order_seq": "X", "intended_long": true, "pending_qty": 95.0}')
    b = FakeBroker([100.0])
    t = AlpacaTrader(b, "SPY", StrategyParams(trail=2), state_file=str(sf),
                     journal_file=str(tmp_path / "j.jsonl"))
    assert t.strat.state == "flat"                      # did NOT half-adopt the long
    assert t.intended_long is False
    assert any("state_load_failed" in l for l in open(tmp_path / "j.jsonl"))


def test_buy_survives_post_fill_position_lag(tmp_path):
    # The order fills but the positions endpoint lags every read this cycle. The
    # engine must stay LONG (off the fill), not flip to flat and halt next cycle.
    b = FakeBroker([100.0])
    b.hide_position = 99                                # position() lags indefinitely this cycle
    t = _trader(b, tmp_path, trail=2)
    t.step()
    assert t.strat.state == "long"                      # held off the fill, not orphaned
    assert t.pending_qty == 95.0
    assert t.intended_long is True


def test_corrupt_state_file_recovers_instead_of_crashing(tmp_path):
    sf = tmp_path / "state.json"
    sf.write_text("{ corrupt json")
    b = FakeBroker([100.0])
    p = StrategyParams(trail=2, reentry=1)
    t = AlpacaTrader(b, "SPY", p, state_file=str(sf), journal_file=str(tmp_path / "j.jsonl"))
    assert t.strat.state == "flat"                      # fell back to a fresh engine
    assert any("state_load_failed" in l for l in open(tmp_path / "j.jsonl"))


def test_restart_does_not_double_buy(tmp_path):
    b = FakeBroker([100.0, 101.0])
    t1 = _trader(b, tmp_path)
    t1.step()
    assert len([o for o in b.orders if o[0] == "buy"]) == 1
    t2 = _trader(b, tmp_path)                            # reload state, broker still holds
    t2.step()
    assert len([o for o in b.orders if o[0] == "buy"]) == 1


def test_unfilled_buy_uses_a_fresh_client_order_id(tmp_path):
    # An order that submits but does not fill must NOT reuse its client_order_id
    # next cycle (Alpaca 422s a reused id -> wedged flat forever).
    b = FakeBroker([100.0, 100.0], fill_ratio=0.0, reject_dupe_coid=True)
    t = _trader(b, tmp_path)
    t.step()                                            # submits SPY-0-buy, unfilled
    t.step()                                            # must submit a FRESH coid
    assert b.coids == ["SPY-0-buy", "SPY-1-buy"]
    assert t.strat.state == "flat"


def test_total_drawdown_limit_halts_on_slow_bleed(tmp_path):
    # ~4%/day for several days: each day is UNDER the 5% daily limit (which
    # re-anchors to the prior close), but cumulative drawdown from the 10000 peak
    # reaches 15% — only the total-drawdown limit catches this.
    b = FakeBroker([100.0] * 8)
    t = _trader(b, tmp_path)
    eqs = [10_000, 9_600, 9_220, 8_850, 8_500]
    days = ["2024-03-01", "2024-03-04", "2024-03-05", "2024-03-06", "2024-03-07"]
    result = None
    for eq, day in zip(eqs, days):
        b.equity = float(eq)
        b.timestamp = f"{day}T10:00:00-05:00"
        result = t.step()
        if result == "halt":
            break
    assert result == "halt"
    assert b.flatten_calls == 1
    assert risk.kill_switch_active()
    assert any("total drawdown" in l for l in open(t.journal_file))   # not the daily limit


def test_flat_reads_reset_on_held_read_blocks_nonconsecutive_confirm(tmp_path):
    # Empty reads separated by a HELD read must NOT accumulate to a confirmed
    # flat — flat_reads resets whenever the position is seen.
    b = FakeBroker([100.0])
    t = _trader(b, tmp_path, trail=2)
    t.strat.state = "long"; t.strat.entry_price = 100.0; t.strat.peak = 100.0
    t.intended_long = True; t.pending_qty = 95.0
    b.position_script = deque([None, {"qty": 95.0, "avg_entry_price": 100.0}, None])
    assert t.reconcile(100.0) == "wait"                # empty #1
    assert t.reconcile(100.0) == "ok"                  # held -> resets flat_reads
    assert t.reconcile(100.0) == "wait"                # empty again, only #1 consecutive
    assert t.strat.state == "long"                     # never falsely confirmed flat


def test_flat_reads_reset_on_read_error(tmp_path):
    # A position() ERROR between two empty reads is not evidence of flat; it must
    # reset the consecutive counter so [empty, ERR, empty] does not confirm flat.
    b = FakeBroker([100.0])
    t = _trader(b, tmp_path, trail=2)
    t.strat.state = "long"; t.strat.entry_price = 100.0; t.strat.peak = 100.0
    t.intended_long = True; t.pending_qty = 95.0
    b.position_script = deque([None, "ERR", None])
    assert t.reconcile(100.0) == "wait"                # empty #1
    with pytest.raises(BrokerError):
        t.reconcile(100.0)                             # error resets flat_reads, re-raises
    assert t.reconcile(100.0) == "wait"                # empty again, only #1 (not confirmed)
    assert t.strat.state == "long"


def test_reconcile_rejects_position_of_wrong_size(tmp_path):
    # intended_long True but the broker holds a size we never ordered -> halt,
    # do not adopt (guards a torn/edited state file).
    b = FakeBroker([100.0])
    b._pos = {"qty": 500.0, "avg_entry_price": 50.0}
    t = _trader(b, tmp_path)
    t.intended_long = True
    t.pending_qty = 95.0                                # we ordered 95, broker has 500
    assert t.reconcile(100.0) == "halt"                 # halts, not adopted
    assert t.strat.state == "flat"


if __name__ == "__main__":
    sys.exit(pytest.main([__file__, "-q"]))
