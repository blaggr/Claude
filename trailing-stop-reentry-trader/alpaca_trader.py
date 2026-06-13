"""Paper-trade the trailing-stop / re-entry rule on Alpaca — broker-managed stop.

After five rounds of review proved that managing the stop inside a client poll
loop cannot be made race-safe (orders and positions are two eventually-consistent
systems), the exit is now a **server-side trailing-stop order**: on entry we place
a resting SELL ``trailing_stop`` order, and the broker tracks the peak and fires
the stop even if this process crashes, lags, or hits a 503 storm. The client only:

  * decides ENTRIES (idempotent client_order_id), and on each entry attaches the
    protective trailing stop (or flattens if it cannot be attached — never naked);
  * notices when the stop has fired and arms re-entry off the real exit price;
  * runs the account-level interlocks (kill switch, daily loss, total drawdown).

A lagging position read now only delays re-entry (harmless) instead of risking a
double-buy or an abandoned, stop-less position.

    export ALPACA_KEY_ID=PK...  ALPACA_SECRET_KEY=...
    python alpaca_trader.py --symbol SPY --trail 1.5 --reentry 1 --poll 60

Live trading stays locked behind the interlocks in :mod:`risk` (env flag + ack
file); by default everything is paper.
"""
from __future__ import annotations

import argparse
import datetime as dt
import json
import math
import os
import signal
import sys
import time
from typing import Optional

import risk
from broker import AlpacaBroker, Broker, BrokerError

_running = True
POSITION_RETRIES = 3       # in-cycle position() reads to tolerate the eventually-consistent endpoint
POSITION_SETTLE = 0.25     # seconds between in-cycle position retries
_STOP_DONE = ("filled", "canceled", "expired", "rejected", "done_for_day")


def _stop(signum, frame):  # pragma: no cover - signal handler
    global _running
    _running = False
    print("\nStopping Alpaca trader (state saved)...")


class AlpacaTrader:
    def __init__(self, broker: Broker, symbol: str, trail: float, reentry: float,
                 enter_at_start: bool = True,
                 state_file: str = "alpaca_state.json",
                 journal_file: str = "alpaca_journal.jsonl"):
        self.broker = broker
        self.symbol = symbol.upper()
        self.trail = float(trail)
        self.reentry = float(reentry)
        self.enter_at_start = bool(enter_at_start)
        self.state_file = state_file
        self.journal_file = journal_file
        # state
        self.mode = "flat"                       # "flat" | "long"
        self.last_exit_price: Optional[float] = None
        self.entry_price: Optional[float] = None
        self.held_qty = 0.0
        self.stop_order_id: Optional[str] = None
        self.armed = False                       # has the first-ever entry been taken?
        self.order_seq = 0
        self.day_start_equity: Optional[float] = None
        self.day: Optional[str] = None
        self.last_equity: Optional[float] = None
        self.peak_equity: Optional[float] = None
        self._load()

    # --------------------------------------------------------- persistence
    @staticmethod
    def _as_float(v) -> Optional[float]:
        try:
            f = None if v is None else float(v)
        except (TypeError, ValueError):
            return None
        return f if (f is not None and math.isfinite(f)) else None

    def _load(self) -> None:
        if not (self.state_file and os.path.exists(self.state_file)):
            return
        try:
            with open(self.state_file) as f:
                d = json.load(f)
            mode = d["mode"] if d.get("mode") in ("flat", "long") else "flat"
            order_seq = int(d.get("order_seq", 0) or 0)
            stop_order_id = d.get("stop_order_id")
            armed = bool(d.get("armed", False))
            last_exit = self._as_float(d.get("last_exit_price"))
            entry = self._as_float(d.get("entry_price"))
            held = self._as_float(d.get("held_qty")) or 0.0
            dse = self._as_float(d.get("day_start_equity"))
            le = self._as_float(d.get("last_equity"))
            pe = self._as_float(d.get("peak_equity"))
            day = d.get("day")
        except (json.JSONDecodeError, KeyError, TypeError, ValueError) as exc:
            self._journal("state_load_failed", {"error": str(exc)})
            return
        self.mode = mode
        self.order_seq = order_seq
        self.stop_order_id = stop_order_id
        self.armed = armed
        self.last_exit_price = last_exit
        self.entry_price = entry
        self.held_qty = held
        self.day_start_equity = dse
        self.last_equity = le
        self.peak_equity = pe
        self.day = day

    def _save(self) -> None:
        if not self.state_file:
            return
        tmp = f"{self.state_file}.tmp"
        with open(tmp, "w") as f:
            json.dump({"mode": self.mode, "last_exit_price": self.last_exit_price,
                       "entry_price": self.entry_price, "held_qty": self.held_qty,
                       "stop_order_id": self.stop_order_id, "armed": self.armed,
                       "order_seq": self.order_seq, "day": self.day,
                       "day_start_equity": self.day_start_equity,
                       "last_equity": self.last_equity, "peak_equity": self.peak_equity},
                      f, indent=2, allow_nan=False)
        os.replace(tmp, self.state_file)

    def _journal(self, event: str, fields: dict) -> dict:
        rec = {"ts": dt.datetime.now().isoformat(timespec="seconds"),
               "symbol": self.symbol, "event": event, "mode": getattr(self, "mode", "?"),
               **fields}
        if self.journal_file:
            with open(self.journal_file, "a") as f:
                f.write(json.dumps(rec) + "\n")
        return rec

    def _next_coid(self, tag: str) -> str:
        coid = f"{self.symbol}-{self.order_seq}-{tag}"
        self.order_seq += 1
        return coid

    # --------------------------------------------------------- broker reads
    def _poll_position(self):
        """position() with brief retries for the eventually-consistent endpoint.
        Returns the held position (qty>0) or None if every retry is empty. A read
        error is swallowed to None — callers here are not safety-critical because
        the protective stop already rests at the broker."""
        for i in range(POSITION_RETRIES):
            try:
                pos = self.broker.position(self.symbol)
            except BrokerError:
                pos = None
            if pos and pos["qty"] > 0:
                return pos
            if i < POSITION_RETRIES - 1:
                time.sleep(POSITION_SETTLE)
        return None

    def _stop_is_open(self) -> bool:
        if not self.stop_order_id:
            return False
        try:
            o = self.broker.get_order(self.stop_order_id)
        except BrokerError:
            return True            # can't tell -> assume it's still resting (don't double-place)
        return bool(o) and o.get("status") not in _STOP_DONE

    def _stop_fill_price(self) -> Optional[float]:
        if not self.stop_order_id:
            return None
        try:
            o = self.broker.get_order(self.stop_order_id)
        except BrokerError:
            return None
        if o and o.get("status") == "filled":
            return self._as_float(o.get("filled_avg_price"))
        return None

    def _place_stop(self, qty: float) -> bool:
        """Attach a protective server-side trailing stop. Returns True on success."""
        coid = self._next_coid("stop")
        try:
            o = self.broker.submit_trailing_stop(self.symbol, int(qty), self.trail,
                                                 client_order_id=coid)
        except BrokerError as exc:
            self._journal("stop_submit_failed", {"error": str(exc)})
            return False
        self.stop_order_id = o.get("id")
        self._journal("STOP_PLACED", {"qty": int(qty), "trail": self.trail,
                                      "order_id": self.stop_order_id})
        return True

    # --------------------------------------------------------- one cycle
    def step(self) -> str:
        if risk.kill_switch_active():
            self._flatten_and_halt("kill switch present")
            return "halt"

        clock = self.broker.clock()
        today = str(clock.get("timestamp", ""))[:10]
        if today and today != self.day:
            self.day = today
            self.day_start_equity = self.last_equity      # carry prior close as the baseline

        if not clock.get("is_open"):
            self._save()
            self._journal("market_closed", {})
            return "closed"

        acct = self.broker.account()
        self.last_equity = acct["equity"]
        self.peak_equity = max(self.peak_equity or acct["equity"], acct["equity"])
        if self.day_start_equity is None:
            self.day_start_equity = acct["equity"]
        if risk.daily_loss_breached(self.day_start_equity, acct["equity"]):
            risk.trip_kill_switch(f"daily loss: {acct['equity']:.2f} vs {self.day_start_equity:.2f}")
            self._flatten_and_halt("daily loss limit breached")
            return "halt"
        if risk.total_drawdown_breached(self.peak_equity, acct["equity"]):
            risk.trip_kill_switch(f"drawdown: {acct['equity']:.2f} vs peak {self.peak_equity:.2f}")
            self._flatten_and_halt("total drawdown limit breached")
            return "halt"

        price = self.broker.last_price(self.symbol)
        status = self._sync(price)
        if status == "halt":
            self._save()
            return "halt"

        if self.mode == "flat" and self._should_enter(price):
            self._enter(price)

        self._save()
        return "ok"

    def _should_enter(self, price: float) -> bool:
        if not self.armed:
            if self.enter_at_start:
                return True
            # Wait-for-trigger mode: arm the re-entry trigger at the first price
            # (mirrors the backtest), so it can ever fire instead of deadlocking.
            self.last_exit_price = price
            self.armed = True
            self._journal("armed_reentry", {"trigger": price + self.reentry})
            return False
        if self.last_exit_price is None:
            return False
        return price >= self.last_exit_price + self.reentry

    def _exit_to_flat(self, exit_px: float, event: str) -> None:
        self.last_exit_price = exit_px
        self.mode = "flat"
        self.entry_price = None
        self.held_qty = 0.0
        self.stop_order_id = None
        self._journal(event, {"exit_price": exit_px})

    def _ensure_protected(self, pos: dict) -> bool:
        """Make sure a resting stop protects the held position; adopt an existing
        open order or place a new one. Returns False if it cannot be protected."""
        if self._stop_is_open():
            return True
        try:
            existing = self.broker.open_orders(self.symbol)
        except BrokerError:
            existing = []
        if existing:                       # a resting stop already protects it — adopt it
            self.stop_order_id = existing[0].get("id")
            return True
        self._journal("stop_missing_resubmit", {})    # no protection found — place one
        return self._place_stop(pos["qty"])

    # --------------------------------------------------------- sync to broker truth
    def _sync(self, price: float) -> str:
        try:
            pos = self.broker.position(self.symbol)
        except BrokerError:
            # Could not read. The protective stop rests at the broker, so a read
            # failure is NOT evidence of a close — keep our current view.
            return "ok"
        if self.mode == "long":
            if pos and pos["qty"] > 0:
                self.held_qty = pos["qty"]
                if not self._ensure_protected(pos):
                    self._flatten_and_halt("could not re-place protective stop")
                    return "halt"
                return "ok"
            # Position reads empty. Decide if it is a REAL close or just lag:
            fill = self._stop_fill_price()
            if fill is not None:                       # the stop genuinely fired
                self._exit_to_flat(fill, "STOPPED_OUT")
                return "ok"
            if not self._stop_is_open():               # position gone AND stop gone -> closed
                self._exit_to_flat(price, "closed_externally")
                return "ok"
            # empty position but the stop is still resting -> transient lag; stay long
            self._journal("position_lag_holding", {})
            return "ok"
        # flat
        if pos and pos["qty"] > 0:
            # Hold while believing flat (crash-window entry). Adopt and ensure a
            # protective stop rather than leaving a naked position.
            self.mode = "long"
            self.held_qty = pos["qty"]
            self.entry_price = pos["avg_entry_price"]
            if not self._ensure_protected(pos):
                self._flatten_and_halt("held unprotected position, could not place stop")
                return "halt"
            self._journal("adopt_long", {"qty": pos["qty"], "entry": pos["avg_entry_price"]})
        return "ok"

    # --------------------------------------------------------- entry
    def _enter(self, price: float) -> None:
        # Only enter when the broker confirms we are truly flat — no position AND
        # no resting order. This makes a double-buy impossible regardless of any
        # position-read lag or a premature flat in _sync.
        try:
            if self.broker.position(self.symbol) or self.broker.open_orders(self.symbol):
                self._journal("skip_buy", {"reason": "not flat at broker"})
                return
        except BrokerError:
            self._journal("skip_buy", {"reason": "could not confirm flat at broker"})
            return
        acct = self.broker.account()
        qty = risk.entry_qty(acct["cash"], price)
        if qty < 1:
            self._journal("skip_buy", {"reason": "insufficient cash", "cash": acct["cash"]})
            return
        coid = self._next_coid("buy")
        self._save()                              # persist consumed seq before the order
        try:
            fill = self.broker.buy(self.symbol, qty, client_order_id=coid)
        except BrokerError as exc:
            self._journal("buy_rejected", {"error": str(exc)})
            return
        pos = self._poll_position()
        held = (pos["qty"] if pos and pos["qty"] >= 1
                else (fill["filled_qty"] if fill and fill["filled_qty"] >= 1 else 0))
        if held < 1:
            # Nothing confirmed held. The idempotent coid makes a retry safe; the
            # next cycle's _sync adopts a lagged fill if one appears.
            self._journal("buy_unconfirmed", {})
            return
        self.entry_price = pos["avg_entry_price"] if pos else fill["fill_price"]
        self.held_qty = held
        self.armed = True
        # Attach the protective stop IMMEDIATELY. If it cannot be placed, do not
        # hold a naked position — flatten and stay out.
        if not self._place_stop(held):
            self.broker.flatten_all()
            self.mode = "flat"
            self.entry_price = None
            self.held_qty = 0.0
            self._journal("entry_unprotected_flattened", {})
            return
        self.mode = "long"
        self._journal("BUY", {"qty": held, "fill_price": self.entry_price})

    # --------------------------------------------------------- halt
    def _flatten_and_halt(self, reason: str) -> None:
        if self.stop_order_id:
            self.broker.cancel_order(self.stop_order_id)
        self.broker.flatten_all()
        confirmed_empty = True
        for i in range(POSITION_RETRIES):
            try:
                pos = self.broker.position(self.symbol)
            except BrokerError:
                confirmed_empty = False
                break
            if pos and pos["qty"] > 0:
                confirmed_empty = False
                break
            if i < POSITION_RETRIES - 1:
                time.sleep(POSITION_SETTLE)
        if not confirmed_empty:
            self._save()
            self._journal("halt_flatten_unconfirmed", {"reason": reason})
            return
        self.mode = "flat"
        self.entry_price = None
        self.held_qty = 0.0
        self.stop_order_id = None
        self._save()
        self._journal("halt", {"reason": reason})

    # --------------------------------------------------------- loop
    def run(self, iterations: int = 0, poll: float = 60.0) -> int:
        global _running
        _running = True
        consecutive_failures, max_failures = 0, 8
        i = 0
        while _running:
            i += 1
            try:
                status = self.step()
                consecutive_failures = 0
            except BrokerError as exc:
                consecutive_failures += 1
                print(f"  broker error ({consecutive_failures}/{max_failures}): {exc}")
                # A read/transient failure is survivable: the protective stop rests
                # at the broker, so we keep looping rather than abandoning it.
                if consecutive_failures >= max_failures:
                    print("  pausing after repeated broker errors (stop remains at broker).")
                    return 1
                status = "error"
            if status == "halt":
                return 0
            if iterations and i >= iterations:
                break
            _sleep(poll)
        return 0


def _sleep(seconds: float) -> None:
    end = time.time() + seconds
    while _running and time.time() < end:
        time.sleep(min(0.5, max(0.0, end - time.time())))


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description=__doc__,
                                formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--symbol", required=True, help="Ticker to paper-trade, e.g. SPY")
    p.add_argument("--trail", type=float, default=1.0, help="Trailing stop distance in $")
    p.add_argument("--reentry", type=float, default=1.0, help="Re-entry trigger $ above last exit")
    p.add_argument("--poll", type=float, default=60.0, help="Seconds between cycles")
    p.add_argument("--iterations", type=int, default=0, help="Stop after N cycles (0 = until Ctrl-C)")
    p.add_argument("--no-start-entry", action="store_true",
                   help="Wait for a re-entry trigger instead of buying immediately")
    p.add_argument("--state-file", default="alpaca_state.json")
    p.add_argument("--journal-file", default="alpaca_journal.jsonl")
    p.add_argument("--check", action="store_true", help="Preflight: verify keys/account/clock, then exit")
    return p


def main(argv=None) -> int:
    args = build_parser().parse_args(argv)
    signal.signal(signal.SIGINT, _stop)
    base_url, mode = risk.resolve_mode()
    broker = AlpacaBroker(base_url, os.environ.get("ALPACA_KEY_ID", ""),
                          os.environ.get("ALPACA_SECRET_KEY", ""), allow_live=(mode == "LIVE"))
    if args.check:
        acct = broker.account()
        clock = broker.clock()
        print(f"[{mode}] account status={acct.get('status')} "
              f"equity=${acct['equity']:,.2f} cash=${acct['cash']:,.2f}")
        print(f"market open={clock.get('is_open')}  "
              f"last {args.symbol.upper()}=${broker.last_price(args.symbol.upper()):.2f}")
        print("preflight OK — paper" if mode == "PAPER" else "preflight OK — LIVE (real money)")
        return 0
    trader = AlpacaTrader(broker, args.symbol, args.trail, args.reentry,
                          enter_at_start=not args.no_start_entry,
                          state_file=args.state_file, journal_file=args.journal_file)
    print(f"[{mode}] trailing-stop trader on {trader.symbol} "
          f"(trail ${trader.trail:g}, re-entry +${trader.reentry:g}, broker-managed stop). "
          f"{'PAPER — no real money.' if mode == 'PAPER' else 'LIVE — REAL MONEY.'} Ctrl-C to stop.")
    return trader.run(iterations=args.iterations, poll=args.poll)


if __name__ == "__main__":
    sys.exit(main())
