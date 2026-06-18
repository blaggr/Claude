"""Offline tests for risk-based sizing + correlation-aware portfolio caps.

No network, no numpy/pandas -- mirrors the rest of the agent test suite.
Covers: fractional Kelly behaviour, the vol/equity monotonicity of vol
targeting, the absolute notional cap, and that the correlation check shrinks
(or rejects) a second highly-correlated, same-direction leg relative to sizing
it standalone.
"""
import os
import sys

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from agent.sizing import (
    PortfolioSizer,
    fractional_kelly_fraction,
    vol_target_qty,
)


# ------------------------------------------------------------ kelly fraction
def test_kelly_zero_at_or_below_half():
    assert fractional_kelly_fraction(0.5, 1.0, 1.0) == 0.0
    assert fractional_kelly_fraction(0.4, 1.0, 1.0) == 0.0


def test_kelly_increases_with_p():
    f55 = fractional_kelly_fraction(0.55, 1.0, 1.0)
    f65 = fractional_kelly_fraction(0.65, 1.0, 1.0)
    f80 = fractional_kelly_fraction(0.80, 1.0, 1.0)
    assert 0.0 < f55 < f65 < f80


def test_kelly_fraction_multiplier_scales_down():
    full = fractional_kelly_fraction(0.7, 1.0, 1.0, fraction=1.0)
    quarter = fractional_kelly_fraction(0.7, 1.0, 1.0, fraction=0.25)
    assert quarter == pytest.approx(0.25 * full)


# ------------------------------------------------------------ vol targeting
def test_higher_vol_fewer_shares():
    # same equity/price/edge; only the instrument vol differs. A strong edge
    # keeps the Kelly lens loose so vol targeting is the binding constraint.
    low = vol_target_qty(100_000, 100.0, 0.95, 20.0, vol_annual=0.15,
                         risk_pct=0.5, kelly_fraction=1.0, max_notional_pct=100.0)
    high = vol_target_qty(100_000, 100.0, 0.95, 20.0, vol_annual=0.55,
                          risk_pct=0.5, kelly_fraction=1.0, max_notional_pct=100.0)
    assert low > high > 0


def test_higher_equity_more_shares():
    small = vol_target_qty(50_000, 100.0, 0.95, 20.0, vol_annual=0.20,
                           risk_pct=0.5, kelly_fraction=1.0)
    large = vol_target_qty(200_000, 100.0, 0.95, 20.0, vol_annual=0.20,
                           risk_pct=0.5, kelly_fraction=1.0)
    assert large > small > 0


def test_no_edge_no_shares():
    assert vol_target_qty(100_000, 100.0, 0.50, 3.0, vol_annual=0.20) == 0


def test_absolute_notional_cap_respected():
    # huge edge + low vol would otherwise size enormous; cap pins notional
    equity, price = 100_000.0, 100.0
    qty = vol_target_qty(equity, price, 0.95, 20.0, vol_annual=0.10,
                         risk_pct=50.0, kelly_fraction=1.0, max_notional_pct=25.0)
    assert qty * price <= 0.25 * equity + price  # within one share of the cap
    # and it is actually binding here (cap of 25% -> 250 shares at $100)
    assert qty == 250


# ------------------------------------------------------------ portfolio sizer
def test_size_standalone_positive():
    s = PortfolioSizer()
    leg = {"instrument": "SPY", "side": "SELL", "probability": 0.7,
           "expected_move_pct": -2.0}
    qty = s.size(leg, equity=100_000, price=600.0, current_positions={})
    assert qty > 0


def test_correlation_check_shrinks_same_direction_leg():
    s = PortfolioSizer(gross_corr_cap_pct=20.0)
    equity = 100_000.0
    # standalone FXI short
    fxi_leg = {"instrument": "FXI", "side": "SELL", "probability": 0.7,
               "expected_move_pct": -3.0}
    standalone = s.size(fxi_leg, equity, price=38.0, current_positions={})
    assert standalone > 0

    # now we already hold a large SPY short (same risk-off / negative SPY-beta
    # direction); the FXI short adds to that net exposure and should be shrunk
    big_spy_short = {"SPY": {"qty": -60, "price": 600.0}}  # -60*600*~0.45 beta
    constrained = s.size(fxi_leg, equity, price=38.0,
                         current_positions=big_spy_short)
    assert constrained < standalone


def test_correlation_check_can_reject_when_no_room():
    s = PortfolioSizer(gross_corr_cap_pct=20.0)
    equity = 100_000.0
    fxi_leg = {"instrument": "FXI", "side": "SELL", "probability": 0.7,
               "expected_move_pct": -3.0}
    # an SPY short already past the correlated-exposure cap on its own
    maxed = {"SPY": {"qty": -120, "price": 600.0}}  # |exposure| ~ 32k > 20k cap
    assert s.size(fxi_leg, equity, price=38.0, current_positions=maxed) == 0


def test_diversifying_leg_not_shrunk():
    s = PortfolioSizer(gross_corr_cap_pct=20.0)
    equity = 100_000.0
    # hold a big SPY long (net positive SPY-beta exposure)
    big_spy_long = {"SPY": {"qty": 120, "price": 600.0}}
    # a GLD long is a diversifier (low/negative SPY beta) -> not constrained,
    # and a SELL SPY would reduce net exposure -> also not constrained
    gld_leg = {"instrument": "GLD", "side": "BUY", "probability": 0.65,
               "expected_move_pct": 1.5}
    standalone = s.size(gld_leg, equity, price=310.0, current_positions={})
    with_book = s.size(gld_leg, equity, price=310.0,
                       current_positions=big_spy_long)
    assert with_book == standalone

    spy_hedge = {"instrument": "SPY", "side": "SELL", "probability": 0.65,
                 "expected_move_pct": 1.5}
    standalone_spy = s.size(spy_hedge, equity, price=600.0, current_positions={})
    hedge = s.size(spy_hedge, equity, price=600.0,
                   current_positions=big_spy_long)
    assert hedge == standalone_spy


# ------------------------------------------------------------ table overrides
def test_constructor_vol_override():
    s = PortfolioSizer(vol={"FOO": 0.99})
    assert s.vol_for("foo") == 0.99
    assert s.vol_for("UNKNOWN") == s.default_vol


def test_correlation_symmetric_and_default():
    s = PortfolioSizer()
    assert s.correlation("SPY", "QQQ") == s.correlation("QQQ", "SPY")
    assert s.correlation("SPY", "SPY") == 1.0
    # an unlisted pair falls back to the default
    assert s.correlation("AAPL", "USO") == s.default_corr
