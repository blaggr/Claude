"""Automated exits for the agent's positions — trailing stop + hard boundary.

The calibrated edges this agent trades are overnight/intraday: the move is
priced by the next cash open (or the session close), and there is no
continuation. So a position must be closed by two mechanisms, whichever fires
first:

  * TRAILING STOP — impulse decay. A long trails below its running high, a short
    above its running low; once price gives back ``trail_pct`` of the extreme,
    flatten. The trail distance is 40% of the calibrated move (floored/capped),
    so thin-vol legs aren't stopped by noise and fat-vol legs don't round-trip.
  * HARD BOUNDARY — time. Anchored to the entry per the calibration: a pre-cash
    entry exits at 09:30 ET, an RTH entry by 15:55 ET, an after-hours/weekend
    entry at the next session's 09:30 ET. Never hold past it.

This mirrors experiments/simulation/intraday.py (TrailingTracker / boundary_after
/ trail_pct_for) but is reimplemented in pure stdlib (datetime + zoneinfo) so the
agent package keeps its zero-dependency, offline-testable posture — importing the
sim module would pull in pandas.
"""
from __future__ import annotations

import datetime as dt
from zoneinfo import ZoneInfo

NY = ZoneInfo("America/New_York")
RTH_START = dt.time(9, 30)
RTH_LAST = dt.time(15, 55)


def trail_pct_for(expected_move_pct: float) -> float:
    """40% of the calibrated move, floored at 0.3% and capped at 1.5%."""
    return min(max(0.4 * abs(expected_move_pct) / 100.0, 0.003), 0.015)


class TrailingTracker:
    """Bidirectional trailing stop. ``update`` returns True on stop-out.
    ``side`` is the position's entry side: 'BUY' = long, 'SELL' = short."""

    def __init__(self, side: str, trail_pct: float, best: float):
        self.long = side.upper() == "BUY"
        self.trail = trail_pct
        self.best = best

    def update(self, price: float) -> bool:
        if self.long:
            self.best = max(self.best, price)
            return price <= self.best * (1 - self.trail)
        self.best = min(self.best, price)
        return price >= self.best * (1 + self.trail)


def ny_now() -> dt.datetime:
    return dt.datetime.now(tz=NY)


def boundary_after(entry: dt.datetime) -> dt.datetime:
    """Hard-exit boundary for an entry at ``entry`` (any tz -> NY): pre-cash ->
    same-day 09:30; RTH -> same-day 15:55; after-hours/weekend -> next weekday
    09:30."""
    t = entry.astimezone(NY)
    tod = t.time()
    midnight = t.replace(hour=0, minute=0, second=0, microsecond=0)
    if t.weekday() < 5 and RTH_START <= tod < RTH_LAST:
        return midnight.replace(hour=15, minute=55)
    if t.weekday() < 5 and tod < RTH_START:
        return midnight.replace(hour=9, minute=30)
    d = midnight + dt.timedelta(days=1)
    while d.weekday() >= 5:
        d += dt.timedelta(days=1)
    return d.replace(hour=9, minute=30)


def _parse_ts(ts: str) -> dt.datetime:
    d = dt.datetime.fromisoformat(ts)
    return d if d.tzinfo else d.replace(tzinfo=dt.timezone.utc)


class ExitManager:
    """Runs the deterministic exit check over the open-position store and
    flattens anything that has hit its trailing stop or boundary.

    Deliberately mechanical and LLM-free: exits are time/price-driven risk
    management, not a decision to deliberate. It reconciles against the broker
    first so it never closes a position the broker no longer shows.
    """

    def __init__(self, broker, memory, positions, *, allow_network: bool = True,
                 cost_model=None):
        self.broker = broker
        self.memory = memory
        self.positions = positions
        self.allow_network = allow_network
        if cost_model is None:
            from .costs import CostModel
            cost_model = CostModel.from_env()
        self.cost_model = cost_model

    def record_entry(self, symbol: str, side: str, qty: int, price: float,
                     *, window: str = "intraday", expected_move_pct: float = 1.0,
                     entry_ts: dt.datetime | None = None, headline: str = "") -> dict:
        """Register a freshly-opened position with its computed exit plan."""
        entry_ts = entry_ts or ny_now()
        trail = trail_pct_for(expected_move_pct)
        boundary = boundary_after(entry_ts)
        return self.positions.record(
            symbol, side=side, qty=qty, entry_price=price,
            entry_ts=entry_ts.isoformat(timespec="seconds"), window=window,
            trail_pct=trail, boundary=boundary.isoformat(timespec="seconds"),
            headline=headline)

    def _price(self, symbol: str, override: dict | None) -> float | None:
        if override and symbol in override:
            return override[symbol]
        from . import marketdata
        snap = marketdata.snapshot([symbol], allow_network=self.allow_network)
        q = snap.get(symbol)
        return q["price"] if q else None

    def check_and_exit(self, *, now: dt.datetime | None = None,
                       prices: dict[str, float] | None = None) -> list[dict]:
        """Check every open position; flatten those that hit a stop or boundary.
        Returns a list of exit event dicts. ``now``/``prices`` are injectable for
        tests; otherwise real time and a live/delayed/stub quote are used."""
        now = now or ny_now()
        exits = []
        broker_pos = self.broker.positions()
        for symbol, rec in self.positions.all().items():
            # reconcile: if the broker is already flat, drop the stale record
            if symbol not in broker_pos or broker_pos[symbol].get("qty", 0) == 0:
                self.memory.log("exit_reconcile", symbol=symbol,
                                note="broker flat — clearing tracked position")
                self.positions.remove(symbol)
                self.memory.clear_position(symbol)
                continue
            price = self._price(symbol, prices)
            if price is None:
                continue
            boundary = _parse_ts(rec["boundary"])
            reason = None
            if now >= boundary:
                reason = "boundary"
            else:
                trk = TrailingTracker(rec["side"], rec["trail_pct"], rec["best"])
                if trk.update(price):
                    reason = "trailing_stop"
                elif trk.best != rec["best"]:
                    self.positions.update_best(symbol, trk.best)
            if reason:
                ev = self._close(symbol, rec, price, reason)
                if ev:
                    exits.append(ev)
        return exits

    def _close(self, symbol: str, rec: dict, price: float, reason: str) -> dict | None:
        exit_side = "sell" if rec["side"] == "BUY" else "buy"
        qty = int(rec["qty"])
        fill = self.broker.market_order(symbol, exit_side, qty, price)
        if fill.status != "filled":
            self.memory.log("exit_failed", symbol=symbol, reason=reason,
                            note=fill.note)
            return None
        d = 1 if rec["side"] == "BUY" else -1
        gross = d * (fill.price - rec["entry_price"]) * qty
        # net of round-trip transaction costs (spread + slippage + short borrow)
        hold_days = max(0.0, (ny_now() - _parse_ts(rec["entry_ts"])).total_seconds() / 86400.0)
        cost = round(self.cost_model.round_trip_cost(
            symbol, qty, rec["entry_price"], fill.price, rec["side"], hold_days), 2)
        pnl = round(gross - cost, 2)
        ev = {"symbol": symbol, "exit_side": exit_side, "qty": qty,
              "entry": rec["entry_price"], "exit": fill.price, "reason": reason,
              "gross_pnl": round(gross, 2), "cost": cost, "pnl": pnl,
              "mode": getattr(self.broker, "mode", "PAPER")}
        self.memory.log("EXIT", **ev)
        self.positions.remove(symbol)
        self.memory.clear_position(symbol)
        return ev
