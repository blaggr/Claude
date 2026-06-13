"""Paper-trade the trailing-stop / re-entry rule on Alpaca — real orders, fake money.

This is the execution-grade sibling of ``paper.py``: instead of simulating fills
off a yfinance price, it drives the SAME :class:`strategy.StreamingStrategy`
off Alpaca's price feed and places real **paper** orders, reconciling fills and
positions against the broker. Live trading is locked behind the interlocks in
:mod:`risk` (env flag + acknowledgement file); by default everything is paper.

    export ALPACA_KEY_ID=PK...  ALPACA_SECRET_KEY=...
    python alpaca_trader.py --symbol SPY --trail 1.5 --reentry 1 --poll 60

Safety design after review:
  * The engine NEVER commits state the broker didn't confirm. Each cycle snapshots
    the strategy, runs the rule, and rolls back if the resulting order does not
    leave us in the position the engine assumed (failed/partial/unconfirmed).
  * It only manages a position it OPENED. A position it did not open (manual, or
    a different process) halts entries instead of being adopted or liquidated.
  * The daily-loss baseline is carried across the session rollover (prior close),
    so an overnight gap counts against the limit.
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

FLAT_CONFIRM = 2       # consecutive empty position() reads (across cycles) before declaring flat
POSITION_RETRIES = 3   # in-cycle position() reads to tolerate the eventually-consistent endpoint
POSITION_SETTLE = 0.25 # seconds between in-cycle position retries

import risk
from broker import AlpacaBroker, Broker, BrokerError
from strategy import StrategyParams, StreamingStrategy

_running = True


def _stop(signum, frame):  # pragma: no cover - signal handler
    global _running
    _running = False
    print("\nStopping Alpaca trader (state saved)...")


class AlpacaTrader:
    def __init__(self, broker: Broker, symbol: str, params: StrategyParams,
                 state_file: str = "alpaca_state.json",
                 journal_file: str = "alpaca_journal.jsonl"):
        self.broker = broker
        self.symbol = symbol.upper()
        self.state_file = state_file
        self.journal_file = journal_file
        # Safe defaults FIRST, so _journal (which reads self.strat) works even if
        # loading a corrupt state file fails inside _load.
        self.strat = StreamingStrategy(params)
        self.day_start_equity: Optional[float] = None
        self.day: Optional[str] = None
        self.last_equity: Optional[float] = None
        self.peak_equity: Optional[float] = None   # high-water mark for the drawdown limit
        self.intended_long = False     # did WE open / intend the current position?
        self.pending_qty = 0.0         # shares we last ordered (to match on reconcile)
        self.order_seq = 0             # for idempotent client_order_ids
        self.flat_reads = 0            # consecutive empty position() reads while long
        self._load(params)

    # --------------------------------------------------------- persistence
    def _load(self, params: StrategyParams) -> None:
        if not (self.state_file and os.path.exists(self.state_file)):
            return
        try:
            with open(self.state_file) as f:
                d = json.load(f)
            # Parse EVERYTHING into locals first; commit to self.* only once all
            # fields parse. Otherwise a malformed field (e.g. order_seq="X") throws
            # mid-assignment, leaving a half-loaded trader that thinks it is long
            # while its risk baselines are wiped.
            strat = StreamingStrategy.from_dict(d["strat"])
            day = d.get("day")
            intended_long = bool(d.get("intended_long", False))
            order_seq = int(d.get("order_seq", 0) or 0)
            pending_qty = self._as_float(d.get("pending_qty")) or 0.0
            day_start_equity = self._as_float(d.get("day_start_equity"))
            last_equity = self._as_float(d.get("last_equity"))
            peak_equity = self._as_float(d.get("peak_equity"))
        except (json.JSONDecodeError, KeyError, TypeError, ValueError) as exc:
            # self.strat is the safe default assigned in __init__, so this is safe.
            self._journal("state_load_failed", {"error": str(exc)})
            return
        if strat.state == "flat":               # only adopt fresh params when flat
            strat.params = params
        self.strat = strat
        self.day = day
        self.intended_long = intended_long
        self.order_seq = order_seq
        self.pending_qty = pending_qty
        self.day_start_equity = day_start_equity
        self.last_equity = last_equity
        self.peak_equity = peak_equity

    @staticmethod
    def _as_float(v) -> Optional[float]:
        """Parse to a FINITE float, else None. A hand-edited/corrupt state file
        with Infinity/NaN must not poison the risk limits (a non-finite baseline
        or peak silently disables daily-loss / drawdown checks)."""
        try:
            f = None if v is None else float(v)
        except (TypeError, ValueError):
            return None
        return f if (f is not None and math.isfinite(f)) else None

    def _qty_matches(self, broker_qty: float) -> bool:
        """Does a broker position's size match what we last ordered? Used before
        adopting a crash-window position so we never adopt an unrelated holding."""
        if not self.pending_qty:
            return False
        return abs(broker_qty - self.pending_qty) <= max(1.0, 0.05 * self.pending_qty)

    def _poll_position(self):
        """Read position() with brief in-cycle retries to tolerate the
        eventually-consistent positions endpoint. Returns the held position
        (qty > 0) as soon as one read shows it, or None only after every retry
        comes back empty. A read error is swallowed to None (callers that must
        bias to 'still held' check separately)."""
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

    def _save(self) -> None:
        if not self.state_file:
            return
        tmp = f"{self.state_file}.tmp"
        with open(tmp, "w") as f:
            json.dump({"strat": self.strat.to_dict(),
                       "day_start_equity": self.day_start_equity,
                       "day": self.day, "last_equity": self.last_equity,
                       "peak_equity": self.peak_equity,
                       "intended_long": self.intended_long,
                       "pending_qty": self.pending_qty,
                       "order_seq": self.order_seq},
                      f, indent=2, allow_nan=False)   # never persist NaN/Infinity
        os.replace(tmp, self.state_file)

    def _journal(self, event: str, fields: dict) -> dict:
        rec = {"ts": dt.datetime.now().isoformat(timespec="seconds"),
               "symbol": self.symbol, "event": event,
               "state": getattr(self, "strat", None) and self.strat.state, **fields}
        if self.journal_file:
            with open(self.journal_file, "a") as f:
                f.write(json.dumps(rec) + "\n")
        return rec

    # --------------------------------------------------------- reconcile
    def reconcile(self, price: float) -> str:
        """Make the engine agree with the broker's truth. Returns:
          "ok"   — proceed to run the rule this cycle
          "halt" — an unmanaged position is present; stop and wait for a human
          "wait" — broker shows flat but we believe we are long and it is not yet
                   confirmed (the positions endpoint is eventually-consistent);
                   skip trading this cycle so we never re-buy on a transient lag.
        """
        try:
            pos = self.broker.position(self.symbol)
        except BrokerError:
            # A failed read is NOT evidence of flat — reset the consecutive-empty
            # counter and let the run loop's error handling deal with it.
            self.flat_reads = 0
            raise
        if pos and pos["qty"] > 0:
            self.flat_reads = 0
            if self.strat.state == "long":
                self.strat.peak = max(self.strat.peak or pos["avg_entry_price"],
                                      pos["avg_entry_price"])
                return "ok"
            if self.intended_long and self._qty_matches(pos["qty"]):
                self.strat.state = "long"
                self.strat.entry_price = pos["avg_entry_price"]
                self.strat.peak = max(self.strat.peak or 0.0, pos["avg_entry_price"])
                self._journal("reconcile_adopt_long",
                              {"qty": pos["qty"], "avg_entry_price": pos["avg_entry_price"]})
                return "ok"
            self._journal("unmanaged_position_halt",
                          {"qty": pos["qty"], "avg_entry_price": pos["avg_entry_price"],
                           "pending_qty": self.pending_qty})
            return "halt"
        # Broker shows flat.
        if self.strat.state == "long":
            # Could be a real external close OR a transient empty read. Require a
            # few CONSECUTIVE empty reads before abandoning the long, and never
            # trade on a cycle that saw the position empty — otherwise a lagging
            # positions endpoint triggers a second all-in BUY on top of the held
            # position (2x exposure, original shares unmanaged).
            self.flat_reads += 1
            if self.flat_reads < FLAT_CONFIRM:
                self._journal("position_unconfirmed_flat", {"reads": self.flat_reads})
                return "wait"
            self.strat.last_exit_price = price
            self.strat.state = "flat"
            self.strat.entry_price = None
            self.strat.peak = None
            self.intended_long = False
            self.pending_qty = 0.0
            self.flat_reads = 0
            self._journal("reconcile_flat", {"exit_basis": price})
        return "ok"

    # --------------------------------------------------------- one cycle
    def step(self) -> str:
        if risk.kill_switch_active():
            self._flatten_and_halt("kill switch present")
            return "halt"

        clock = self.broker.clock()
        today = str(clock.get("timestamp", ""))[:10]
        if today and today != self.day:
            # New session: carry the prior session's last equity as the loss
            # baseline so an overnight gap counts against the daily limit.
            self.day = today
            self.day_start_equity = self.last_equity

        if not clock.get("is_open"):
            self._save()                       # persist the rollover even when closed
            self._journal("market_closed", {})
            return "closed"

        acct = self.broker.account()
        self.last_equity = acct["equity"]
        self.peak_equity = max(self.peak_equity or acct["equity"], acct["equity"])
        if self.day_start_equity is None:
            self.day_start_equity = acct["equity"]
        if risk.daily_loss_breached(self.day_start_equity, acct["equity"]):
            risk.trip_kill_switch(
                f"daily loss limit: equity {acct['equity']:.2f} "
                f"vs day start {self.day_start_equity:.2f}")
            self._flatten_and_halt("daily loss limit breached")
            return "halt"
        if risk.total_drawdown_breached(self.peak_equity, acct["equity"]):
            risk.trip_kill_switch(
                f"total drawdown limit: equity {acct['equity']:.2f} "
                f"vs peak {self.peak_equity:.2f}")
            self._flatten_and_halt("total drawdown limit breached")
            return "halt"

        price = self.broker.last_price(self.symbol)
        rc = self.reconcile(price)
        if rc == "halt":
            self._save()
            return "halt"
        if rc == "wait":
            self._save()
            return "wait"      # keep looping, but do not trade this cycle

        snapshot = self.strat.to_dict()
        event = self.strat.update(price)
        if event and event["action"] == "BUY":
            if not self._do_buy(price):
                self.strat = StreamingStrategy.from_dict(snapshot)   # not confirmed -> roll back
        elif event and event["action"] == "SELL":
            if not self._do_sell(price):
                self.strat = StreamingStrategy.from_dict(snapshot)   # close failed/partial -> stay long
        else:
            ref = (self.strat.stop_level if self.strat.state == "long"
                   else self.strat.reentry_trigger)
            self._journal("tick", {"price": price, "ref": ref})

        self._save()
        return "ok"

    # --------------------------------------------------------- order paths
    def _do_buy(self, price: float) -> bool:
        """Returns True only if we genuinely hold a position afterwards."""
        acct = self.broker.account()                 # fresh cash after reconcile/waits
        qty = risk.entry_qty(acct["cash"], price)
        if qty < 1:
            self._journal("skip_buy", {"reason": "insufficient cash for one share",
                                       "cash": acct["cash"], "price": price})
            return False
        # Consume a fresh client_order_id PER SUBMISSION (incremented and persisted
        # before the order). Reusing a coid after an unfilled order is rejected by
        # Alpaca with a 422, which would wedge re-entry forever.
        coid = f"{self.symbol}-{self.order_seq}-buy"
        self.order_seq += 1
        self.intended_long = True
        self.pending_qty = float(qty)
        self._save()        # persist consumed seq + intent before the order
        try:
            fill = self.broker.buy(self.symbol, qty, client_order_id=coid)
        except BrokerError as exc:
            self.intended_long = False
            self.pending_qty = 0.0
            self._journal("buy_rejected", {"error": str(exc)})
            return False
        # Determine the held size from the broker, tolerating the eventually-
        # consistent positions endpoint with brief retries. If the order returned
        # a fill, we DEFINITELY hold — never conclude "unfilled" on a lagging
        # position read (that previously flipped us flat on a paid order and then
        # halted on our own position next cycle).
        pos = self._poll_position()
        filled = fill["filled_qty"] if (fill and fill["filled_qty"] >= 1) else 0
        held = pos["qty"] if (pos and pos["qty"] >= 1) else filled
        if held < 1:
            # Ambiguous: no fill reported and no position seen. Keep intended_long
            # and pending_qty so that if this was an extreme-lag fill, the next
            # cycle's reconcile adopts it (size-matched) BEFORE any re-buy. Roll
            # the strategy back to flat for now.
            self._journal("buy_unconfirmed", {})
            return False
        self.strat.entry_price = fill["fill_price"] if fill else pos["avg_entry_price"]
        self.strat.peak = self.strat.entry_price
        self.pending_qty = held                      # actual filled size (handles partials)
        self.flat_reads = 0
        self._journal("BUY", {"qty": held, "fill_price": self.strat.entry_price})
        return True

    def _do_sell(self, price: float) -> bool:
        """Returns True only if the broker is CONFIRMED flat afterwards."""
        try:
            fill = self.broker.close(self.symbol)
        except BrokerError as exc:
            self._journal("sell_failed", {"error": str(exc)})
            return False                              # stay long, retry next loop
        pos = self.broker.position(self.symbol)
        if pos and pos["qty"] > 0:
            self._journal("partial_close", {"remaining": pos["qty"]})
            return False                              # still holding -> stay long, retry
        if fill is None:
            # Nothing was held — position already gone. Arm re-entry off current price.
            self.strat.last_exit_price = price
            self.intended_long = False
            self.pending_qty = 0.0
            self._journal("sell_no_position", {"exit_basis": price})
            return True
        self.strat.last_exit_price = fill["fill_price"]
        self.intended_long = False
        self.pending_qty = 0.0
        self._journal("SELL", {"fill_price": fill["fill_price"]})
        return True

    def _flatten_and_halt(self, reason: str) -> None:
        self.broker.flatten_all()
        # flatten_all is best-effort (it swallows broker errors). Only claim flat
        # if we CONFIRM the position is gone across retries (the positions endpoint
        # lags, and a single empty read after a possibly-failed liquidation is not
        # proof). Bias to "still held": any held read OR a read error keeps us long
        # so a restart re-adopts and retries, rather than abandoning a stop-less
        # position during the exact event (kill / loss / drawdown) when it matters.
        confirmed_empty = True
        for i in range(POSITION_RETRIES):
            try:
                pos = self.broker.position(self.symbol)
            except BrokerError:
                confirmed_empty = False     # could not confirm -> assume held
                break
            if pos and pos["qty"] > 0:
                confirmed_empty = False
                break
            if i < POSITION_RETRIES - 1:
                time.sleep(POSITION_SETTLE)
        if not confirmed_empty:
            self._save()              # keep state long so a restart re-adopts & retries
            self._journal("halt_flatten_unconfirmed", {"reason": reason})
            return
        self.strat.state = "flat"
        self.strat.entry_price = None
        self.strat.peak = None
        self.intended_long = False
        self.pending_qty = 0.0
        self._save()
        self._journal("halt", {"reason": reason})

    # --------------------------------------------------------- loop
    def run(self, iterations: int = 0, poll: float = 60.0) -> int:
        global _running
        _running = True
        consecutive_failures, max_failures = 0, 5
        i = 0
        while _running:
            i += 1
            try:
                status = self.step()
                consecutive_failures = 0
            except BrokerError as exc:
                consecutive_failures += 1
                print(f"  broker error ({consecutive_failures}/{max_failures}): {exc}")
                if consecutive_failures >= max_failures:
                    print("  giving up after repeated broker errors.")
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
    p.add_argument("--poll", type=float, default=60.0, help="Seconds between price polls")
    p.add_argument("--iterations", type=int, default=0, help="Stop after N polls (0 = until Ctrl-C)")
    p.add_argument("--no-start-entry", action="store_true",
                   help="Wait for a re-entry trigger instead of buying immediately")
    p.add_argument("--state-file", default="alpaca_state.json")
    p.add_argument("--journal-file", default="alpaca_journal.jsonl")
    p.add_argument("--check", action="store_true",
                   help="Preflight: verify keys, account and clock, then exit")
    return p


def main(argv=None) -> int:
    args = build_parser().parse_args(argv)
    signal.signal(signal.SIGINT, _stop)

    base_url, mode = risk.resolve_mode()
    broker = AlpacaBroker(base_url,
                          os.environ.get("ALPACA_KEY_ID", ""),
                          os.environ.get("ALPACA_SECRET_KEY", ""),
                          allow_live=(mode == "LIVE"))

    if args.check:
        acct = broker.account()
        clock = broker.clock()
        print(f"[{mode}] account status={acct.get('status')} "
              f"equity=${acct['equity']:,.2f} cash=${acct['cash']:,.2f}")
        print(f"market open={clock.get('is_open')}  "
              f"last price {args.symbol.upper()}=${broker.last_price(args.symbol.upper()):.2f}")
        print("preflight OK — paper" if mode == "PAPER" else "preflight OK — LIVE (real money)")
        return 0

    params = StrategyParams(trail=args.trail, reentry=args.reentry,
                            enter_at_start=not args.no_start_entry)
    trader = AlpacaTrader(broker, args.symbol, params,
                          state_file=args.state_file, journal_file=args.journal_file)
    print(f"[{mode}] trailing-stop trader on {trader.symbol} "
          f"(trail ${params.trail:g}, re-entry +${params.reentry:g}). "
          f"{'PAPER — no real money.' if mode == 'PAPER' else 'LIVE — REAL MONEY.'} Ctrl-C to stop.")
    return trader.run(iterations=args.iterations, poll=args.poll)


if __name__ == "__main__":
    sys.exit(main())
