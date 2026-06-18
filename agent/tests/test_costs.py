"""Offline tests for the transaction-cost & slippage model — no network.

Covers CostModel arithmetic (slippage monotonicity, short-borrow accrual and
its absence for longs, round-trip == entry + exit + borrow, net < gross) and a
smoke test of the rescore CLI that confirms a calibrated leg flips negative
under high slippage.
"""
import json
import os
import sys

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from agent import rescore
from agent.costs import CostModel


# ---------------------------------------------------------------- arithmetic
def test_slippage_monotonicity():
    """More slippage must never reduce cost, and strictly increases it here."""
    lo = CostModel(slippage_bps=3.0)
    hi = CostModel(slippage_bps=50.0)
    c_lo = lo.round_trip_cost("SPY", 100, 600.0, 600.0, "BUY")
    c_hi = hi.round_trip_cost("SPY", 100, 600.0, 600.0, "BUY")
    assert c_hi > c_lo


def test_short_borrow_accrues_with_hold_days():
    cm = CostModel(borrow_rate_annual=0.05)
    b1 = cm.borrow_cost("FXI", 100, 38.0, hold_days=1, side="SELL")
    b10 = cm.borrow_cost("FXI", 100, 38.0, hold_days=10, side="SELL")
    assert b1 > 0
    assert b10 == pytest.approx(b1 * 10)
    # explicit pro-rata formula check
    assert b1 == pytest.approx(100 * 38.0 * 0.05 * 1 / 365.0)


def test_borrow_zero_for_longs():
    cm = CostModel(borrow_rate_annual=0.05)
    assert cm.borrow_cost("SPY", 100, 600.0, hold_days=10, side="BUY") == 0.0


def test_round_trip_equals_entry_exit_borrow():
    cm = CostModel(slippage_bps=3.0, half_spread_bps=2.0,
                   commission_per_share=0.005, borrow_rate_annual=0.02)
    entry = cm.entry_cost("FXI", 100, 38.0)
    ex = cm.exit_cost("FXI", 100, 39.0)
    borrow = cm.borrow_cost("FXI", 100, 38.0, hold_days=3, side="SELL")
    rt = cm.round_trip_cost("FXI", 100, 38.0, 39.0, "SELL", hold_days=3)
    assert rt == pytest.approx(entry + ex + borrow)


def test_net_pnl_reduces_gross():
    cm = CostModel(slippage_bps=10.0)
    gross = 500.0
    net = cm.net_pnl(gross, "SPY", 100, 600.0, 605.0, "BUY")
    assert net < gross
    # net = gross - round_trip_cost
    rt = cm.round_trip_cost("SPY", 100, 600.0, 605.0, "BUY")
    assert net == pytest.approx(gross - rt)


def test_from_env_reads_slippage(monkeypatch):
    monkeypatch.setenv("COST_SLIPPAGE_BPS", "25")
    cm = CostModel.from_env()
    assert cm.slippage_bps == 25.0
    # explicit override beats the env
    cm2 = CostModel.from_env(slippage_bps=7.0)
    assert cm2.slippage_bps == 7.0


# ---------------------------------------------------------------- rescore CLI
def test_rescore_json_smoke(capsys):
    """--json runs and emits parseable output with the expected schema."""
    rc = rescore.main(["--json"])
    assert rc == 0
    out = capsys.readouterr().out
    data = json.loads(out)
    assert data["legs"], "expected at least one calibrated leg"
    leg = data["legs"][0]
    for k in ("topic", "regime", "symbol", "side", "edge_gross_ps",
              "cost_ps", "edge_net_ps", "positive"):
        assert k in leg


def test_high_slippage_flips_a_leg_negative(capsys):
    """Under 50 bps slippage at least one positive-gross leg goes net-negative."""
    rc = rescore.main(["--json", "--slippage-bps", "50"])
    assert rc == 0
    data = json.loads(capsys.readouterr().out)
    flipped = [leg for leg in data["legs"] if leg["flipped_negative"]]
    assert flipped, "expected at least one leg flipped negative under high slippage"
