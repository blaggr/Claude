"""Deliberately pessimistic fill model. Most 'edges' die here."""
from __future__ import annotations
from dataclasses import dataclass


@dataclass
class CostModel:
    half_spread_bps: float = 2.0     # half the bid-ask in basis points
    impact_bps: float = 1.0          # market-impact slippage

    @property
    def _edge_bps(self) -> float:
        return self.half_spread_bps + self.impact_bps

    def fill_buy(self, mid: float) -> float:
        return round(mid * (1 + self._edge_bps / 1e4), 6)

    def fill_sell(self, mid: float) -> float:
        return round(mid * (1 - self._edge_bps / 1e4), 6)
