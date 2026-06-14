"""Replay events into trades. One position at a time; bankroll compounds.
Strict no-look-ahead: exits scan only bars at/after entry."""
from __future__ import annotations
import datetime as dt
from dataclasses import dataclass, field
from typing import Callable, Optional
import pandas as pd
from events import Event, Signal
from prices import first_at_or_after, PriceError
from costs import CostModel


@dataclass
class Trade:
    event_ts: dt.datetime
    symbol: str
    side: str
    entry_ts: dt.datetime
    entry_px: float
    exit_ts: dt.datetime
    exit_px: float
    ret: float                      # net return on the position, after costs
    reason: str


@dataclass
class Result:
    trades: list = field(default_factory=list)
    initial_capital: float = 0.0
    final_equity: float = 0.0
    equity_curve: list = field(default_factory=list)   # (ts, equity)


def _to_ts(ts: dt.datetime) -> pd.Timestamp:
    """Return a tz-aware UTC pd.Timestamp, regardless of input tz state."""
    if ts.tzinfo is None:
        return pd.Timestamp(ts, tz="UTC")
    return pd.Timestamp(ts)


def _exit(bars: pd.DataFrame, entry_ts: dt.datetime, entry_px: float,
          side: str, horizon_min: int, trail: Optional[float]):
    """Walk bars after entry; exit at horizon or trailing stop, whichever first."""
    deadline = entry_ts + dt.timedelta(minutes=horizon_min)
    deadline_ts = _to_ts(deadline)
    entry_ts_ts = _to_ts(entry_ts)
    after = bars[bars["ts"] > entry_ts_ts]
    peak = entry_px
    for _, row in after.iterrows():
        ts_pd = row["ts"]
        ts = ts_pd.to_pydatetime()
        px = float(row["close"])
        if trail is not None:
            if side == "long":
                peak = max(peak, px)
                if px <= peak - trail:
                    return ts, px, "trail"
            else:
                peak = min(peak, px)
                if px >= peak + trail:
                    return ts, px, "trail"
        if ts_pd >= deadline_ts:
            return ts, px, "horizon"
    if not after.empty:                       # ran out of data: exit at last bar
        last = after.iloc[-1]
        return last["ts"].to_pydatetime(), float(last["close"]), "eod"
    return entry_ts, entry_px, "no_exit_data"


def run_backtest(events: list,
                 bars_by_symbol: dict,
                 classify_fn: Callable,
                 cost_model: CostModel,
                 capital: float = 10_000.0) -> Result:
    equity = capital
    res = Result(initial_capital=capital, equity_curve=[])
    for ev in events:
        bars = bars_by_symbol.get(ev.payload.get("symbol"))
        if bars is None:
            continue
        sig = classify_fn(ev, bars)
        if sig is None or sig.entry_ts is None:
            continue
        try:
            entry_ts, mid_in = first_at_or_after(bars, sig.entry_ts)
        except PriceError:
            continue
        entry_px = cost_model.fill_buy(mid_in) if sig.side == "long" else cost_model.fill_sell(mid_in)
        exit_ts, mid_out, reason = _exit(bars, entry_ts, mid_in, sig.side,
                                         sig.horizon_min, sig.trail)
        exit_px = cost_model.fill_sell(mid_out) if sig.side == "long" else cost_model.fill_buy(mid_out)
        ret = (exit_px / entry_px - 1.0) if sig.side == "long" else (entry_px / exit_px - 1.0)
        equity *= (1 + sig.size_frac * ret)
        res.trades.append(Trade(ev.ts, sig.symbol, sig.side, entry_ts, entry_px,
                                exit_ts, exit_px, ret, reason))
        res.equity_curve.append((exit_ts, equity))
    res.final_equity = equity
    return res
