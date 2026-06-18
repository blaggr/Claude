"""Transaction-cost & slippage model for the paper trading agent.

A small, stdlib-only cost model with realistic retail-ETF defaults so that
P&L and expected-edge calculations can be charged for the frictions a real
fill would incur:

  * COMMISSION — per share, plus a per-order minimum. Most US retail brokers
    are commission-free on ETFs, so both default to 0.0.
  * HALF-SPREAD — paid on entry and again on exit; quoted in basis points of
    notional (~2 bps for liquid ETFs like SPY/QQQ).
  * SLIPPAGE — adverse price impact, also per side, in basis points (~3 bps,
    scalable for stress tests).
  * SHORT BORROW — an annualized fee on the short notional, accrued pro-rata
    over the holding period (~1%/yr). Longs never pay it.

Everything is pure arithmetic and deterministic; there is no network and no
third-party dependency. Defaults can be overridden in the constructor or via
environment variables (COST_* — see ``CostModel.from_env``), matching the
repo's existing ``os.environ.get(...)`` configuration pattern.

Costs are always returned as positive dollar amounts (a drag on P&L). Paper /
planning tool only.
"""
from __future__ import annotations

import os
from dataclasses import dataclass

BPS = 1e-4              # one basis point as a fraction
DAYS_PER_YEAR = 365.0   # calendar-day basis for pro-rata borrow accrual


def _envf(name: str, default: float) -> float:
    """Read a float from the environment, falling back to ``default``."""
    try:
        return float(os.environ.get(name, default))
    except (TypeError, ValueError):
        return default


@dataclass
class CostModel:
    """Configurable transaction-cost & slippage assumptions (retail ETF).

    All bps figures are per side (entry and exit each pay them). Costs are
    reported as positive dollars.
    """

    commission_per_share: float = 0.0   # $/share, per side
    min_commission: float = 0.0         # $ floor per order, per side
    half_spread_bps: float = 2.0        # bps of notional, per side
    slippage_bps: float = 3.0           # bps of notional, per side
    borrow_rate_annual: float = 0.01    # annualized short-borrow rate (1%/yr)

    @classmethod
    def from_env(cls, **overrides) -> "CostModel":
        """Build from COST_* env vars; explicit ``overrides`` win over the env.

        Recognized: COST_COMMISSION_PER_SHARE, COST_MIN_COMMISSION,
        COST_SPREAD_BPS, COST_SLIPPAGE_BPS, COST_BORROW_RATE_ANNUAL.
        """
        env = dict(
            commission_per_share=_envf("COST_COMMISSION_PER_SHARE",
                                       cls.commission_per_share),
            min_commission=_envf("COST_MIN_COMMISSION", cls.min_commission),
            half_spread_bps=_envf("COST_SPREAD_BPS", cls.half_spread_bps),
            slippage_bps=_envf("COST_SLIPPAGE_BPS", cls.slippage_bps),
            borrow_rate_annual=_envf("COST_BORROW_RATE_ANNUAL",
                                     cls.borrow_rate_annual),
        )
        env.update(overrides)
        return cls(**env)

    # ---------------------------------------------------------------- per side
    def _commission(self, qty: float) -> float:
        """Commission for one order leg: per-share charge, floored at the min."""
        qty = abs(qty)
        if qty == 0:
            return 0.0
        return max(self.commission_per_share * qty, self.min_commission)

    def _side_cost(self, qty: float, price: float) -> float:
        """Cost of a single fill: half-spread + slippage on notional, plus
        commission. Quantity sign is ignored; result is positive dollars."""
        notional = abs(qty) * abs(price)
        impact = notional * (self.half_spread_bps + self.slippage_bps) * BPS
        return impact + self._commission(qty)

    def entry_cost(self, symbol: str, qty: float, price: float) -> float:
        """Friction paid opening a position (one fill). Positive dollars."""
        return self._side_cost(qty, price)

    def exit_cost(self, symbol: str, qty: float, price: float) -> float:
        """Friction paid closing a position (one fill). Positive dollars."""
        return self._side_cost(qty, price)

    def borrow_cost(self, symbol: str, qty: float, price: float,
                    hold_days: float, side: str) -> float:
        """Short-borrow fee accrued pro-rata over ``hold_days``.

        Charged only for shorts (``side`` SELL/SHORT); zero for longs. The fee
        is ``annual_rate * notional * hold_days / 365``.
        """
        if side.upper() not in ("SELL", "SHORT"):
            return 0.0
        notional = abs(qty) * abs(price)
        days = max(0.0, float(hold_days))
        return notional * self.borrow_rate_annual * days / DAYS_PER_YEAR

    def round_trip_cost(self, symbol: str, qty: float, entry_price: float,
                        exit_price: float, side: str,
                        hold_days: float = 0.0) -> float:
        """Total $ friction for a full round trip: entry + exit + borrow."""
        return (self.entry_cost(symbol, qty, entry_price)
                + self.exit_cost(symbol, qty, exit_price)
                + self.borrow_cost(symbol, qty, entry_price, hold_days, side))

    def net_pnl(self, gross_pnl: float, symbol: str, qty: float,
                entry_price: float, exit_price: float, side: str,
                hold_days: float = 0.0) -> float:
        """Gross P&L minus the round-trip cost. Always <= gross_pnl."""
        cost = self.round_trip_cost(symbol, qty, entry_price, exit_price,
                                    side, hold_days)
        return gross_pnl - cost
