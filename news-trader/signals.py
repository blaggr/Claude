"""Drift signal (B): ride the initial post-release reaction. No look-ahead --
the side is decided from the measurement window and entered at its close."""
from __future__ import annotations
import datetime as dt
from typing import Optional
import pandas as pd
from events import Event, Signal
from prices import first_at_or_after, PriceError


def drift_signal(event: Event, bars: pd.DataFrame, *, delta_s: int,
                 measure_min: int, horizon_min: int, trail: Optional[float],
                 size_frac: float = 0.95) -> Optional[Signal]:
    symbol = event.payload.get("symbol")
    start = event.ts + dt.timedelta(seconds=delta_s)
    end = start + dt.timedelta(minutes=measure_min)
    try:
        _, p0 = first_at_or_after(bars, start)
        _, p1 = first_at_or_after(bars, end)
    except PriceError:
        return None
    reaction = p1 / p0 - 1.0
    if reaction == 0:
        return None
    side = "long" if reaction > 0 else "short"
    return Signal(symbol=symbol, side=side, size_frac=size_frac,
                  horizon_min=horizon_min, trail=trail,
                  confidence=abs(reaction), rationale=f"drift {reaction:+.4%}",
                  entry_ts=end)          # enter at the measurement-window end (no look-ahead)
