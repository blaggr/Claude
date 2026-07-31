"""Contracts every source, signal, and the backtest speak. Pure data."""
from __future__ import annotations
import datetime as dt
from dataclasses import dataclass, field
from typing import Optional


@dataclass(frozen=True)
class Event:
    ts: dt.datetime               # release time, tz-aware UTC
    source: str                   # e.g. "macro"
    type: str                     # e.g. "CPI" | "FOMC" | "NFP"
    payload: dict = field(default_factory=dict)


@dataclass
class Signal:
    symbol: str
    side: str                     # "long" | "short"
    size_frac: float              # fraction of capital in (0, 1]
    horizon_min: int              # holding horizon, minutes
    trail: Optional[float]        # trailing stop in $ (None = no trail)
    confidence: float
    rationale: str
    entry_ts: Optional[dt.datetime] = None   # when to enter (set by the signal; consumed by backtest)
