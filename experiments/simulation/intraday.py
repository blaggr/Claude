"""Event-time intraday fill model for the news simulation.

Replaces the old close→open daily fill (which entered *after* the move our
event studies located in the overnight gap) with fills reconstructed from
1-minute bars:

  * ENTRY  — first minute bar at/after post_time + DETECTION_LATENCY_MIN,
             using pre/post-market bars where they exist. If the first
             tradable bar is already at/after the exit boundary (e.g. a 3am
             post on an instrument with no pre-market liquidity), the event
             is marked MISSED — the move was priced before we could trade.
  * EXIT   — impulse decay via a trailing stop on minute closes (long legs
             trail below the running high, short legs above the running low),
             with a hard boundary per the calibration ("priced by the next
             cash open"):
               - pre-market entry  -> exit at that day's 09:30 open
               - RTH entry         -> exit by the 15:55 close auction window
               - post-market/weekend entry -> exit at the next session's open
  * STALE  — events still unresolved 3+ days after the post are force-closed
             at the last available bar (minute history only spans ~7 days).

Because minute history covers the past ~7 days, a once-daily run reconstructs
exact event-time fills retrospectively — no always-on poller required.
"""
from __future__ import annotations

import datetime as dt

import pandas as pd

NY = "America/New_York"
DETECTION_LATENCY_MIN = 5      # assumed delay between post and our (sim) order
RTH_START = dt.time(9, 30)
RTH_LAST = dt.time(15, 55)     # exit window before the close; 16:00 bar often absent
STALE_AFTER_DAYS = 3


def trail_pct_for(expected_move_pct: float) -> float:
    """Trail distance for the decay exit: 40% of the calibrated move,
    floored/capped so thin-vol legs aren't stopped by noise and fat-vol legs
    don't give the whole move back."""
    return min(max(0.4 * abs(expected_move_pct) / 100.0, 0.003), 0.015)


def fetch_minute_bars(tickers: list[str]) -> dict[str, pd.Series]:
    """~7 days of 1-minute closes per ticker, pre/post-market included,
    tz-converted to New York. Missing tickers map to an empty series."""
    import yfinance as yf

    raw = yf.download(tickers, interval="1m", period="7d", prepost=True,
                      auto_adjust=True, progress=False, group_by="ticker")
    out = {}
    for t in tickers:
        try:
            df = raw[t] if isinstance(raw.columns, pd.MultiIndex) else raw
            s = df["Close"].dropna()
            s.index = s.index.tz_convert(NY)
            out[t] = s[s > 0]
        except Exception:
            out[t] = pd.Series(dtype=float)
    return out


class TrailingTracker:
    """Bidirectional trailing stop on a price stream (the project's original
    exit idea applied minute-by-minute). update() returns True on stop-out."""

    def __init__(self, side: str, trail_pct: float, entry: float):
        self.long = side == "BUY"
        self.trail = trail_pct
        self.best = entry

    def update(self, price: float) -> bool:
        if self.long:
            self.best = max(self.best, price)
            return price <= self.best * (1 - self.trail)
        self.best = min(self.best, price)
        return price >= self.best * (1 + self.trail)


def boundary_after(signal_ts: pd.Timestamp) -> pd.Timestamp:
    """Hard-exit boundary for a signal arriving at signal_ts (NY tz), anchored
    to the POST time per the calibration ("priced by the next cash open"):
    pre-market -> same day 09:30; RTH -> same day 15:55 (flat by the close of
    the session the post lands in); otherwise the next weekday's 09:30."""
    t = signal_ts.tz_convert(NY)
    tod = t.time()
    if t.weekday() < 5 and RTH_START <= tod < RTH_LAST:
        return t.normalize() + pd.Timedelta(hours=15, minutes=55)
    if t.weekday() < 5 and tod < RTH_START:
        return t.normalize() + pd.Timedelta(hours=9, minutes=30)
    d = t.normalize() + pd.Timedelta(days=1)
    while d.weekday() >= 5:
        d += pd.Timedelta(days=1)
    return d + pd.Timedelta(hours=9, minutes=30)


def simulate_leg(closes: pd.Series, post_ts: pd.Timestamp, side: str,
                 trail_pct: float, latency_min: int = DETECTION_LATENCY_MIN,
                 force_close: bool = False) -> dict:
    """Walk one leg through the minute bars. Returns a dict with status:
    'closed' (entry/exit/ret/reason), 'missed' (venue closed until the move
    was priced), or 'open' (not enough data yet — retry next run, or pass
    force_close=True to settle at the last bar)."""
    if closes is None or len(closes) == 0:
        return {"status": "open"}
    t0 = post_ts.tz_convert(NY) + pd.Timedelta(minutes=latency_min)
    sub = closes[closes.index >= t0]
    if sub.empty:
        return {"status": "open"}   # post too recent for available bars

    entry_ts, entry = sub.index[0], float(sub.iloc[0])
    bnd = boundary_after(t0)   # anchored to the post, not the first tradable bar
    if entry_ts >= bnd:
        return {"status": "missed",
                "note": f"first tradable bar {entry_ts:%m-%d %H:%M} is at/after "
                        f"the exit boundary {bnd:%m-%d %H:%M} — move already priced"}

    d = 1 if side == "BUY" else -1
    trk = TrailingTracker(side, trail_pct, entry)
    for ts, price in sub.iloc[1:].items():
        price = float(price)
        if ts >= bnd:
            return _closed(entry_ts, entry, ts, price, d, "boundary")
        if trk.update(price):
            return _closed(entry_ts, entry, ts, price, d, "trailing_stop")

    if force_close:
        ts, price = sub.index[-1], float(sub.iloc[-1])
        if ts > entry_ts:
            return _closed(entry_ts, entry, ts, price, d, "stale_close")
    return {"status": "open", "entry_ts": str(entry_ts), "entry": entry}


def _closed(entry_ts, entry, exit_ts, exit_px, d, reason) -> dict:
    return {"status": "closed", "entry_ts": str(entry_ts), "entry": round(entry, 4),
            "exit_ts": str(exit_ts), "exit": round(exit_px, 4),
            "ret": d * (exit_px / entry - 1), "reason": reason}
