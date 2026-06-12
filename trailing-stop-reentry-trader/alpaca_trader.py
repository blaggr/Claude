"""Paper-trade the trailing-stop / re-entry rule on Alpaca — real orders, fake money.

This is the execution-grade sibling of ``paper.py``: instead of simulating fills
off a yfinance price, it drives the SAME :class:`strategy.StreamingStrategy`
off Alpaca's price feed and places real **paper** orders, reconciling fills and
positions against the broker. Live trading is locked behind the interlocks in
:mod:`risk` (env flag + acknowledgement file); by default everything is paper.

    export ALPACA_KEY_ID=PK...  ALPACA_SECRET_KEY=...
    python alpaca_trader.py --symbol SPY --trail 1.5 --reentry 1 --poll 60

The strategy is all-in / all-out in a single symbol:
  * BUY event  -> market buy a whole-share slice of cash (risk.entry_qty)
  * SELL event -> close the entire position
Entries fire only while the market is open (regular-hours market orders). State
is journaled to JSONL and persisted so a restart reconciles against Alpaca
rather than double-ordering.
"""
from __future__ import annotations

import argparse
import datetime as dt
import json
import os
import signal
import sys
import time
from typing import Optional

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
        self.strat, self.day_start_equity, self.day = self._load(params)

    # --------------------------------------------------------- persistence
    def _load(self, params: StrategyParams):
        if self.state_file and os.path.exists(self.state_file):
            try:
                with open(self.state_file) as f:
                    d = json.load(f)
                strat = StreamingStrategy.from_dict(d["strat"])
                if strat.state == "flat":   # only adopt fresh params when flat
                    strat.params = params
                return strat, d.get("day_start_equity"), d.get("day")
            except (json.JSONDecodeError, KeyError, TypeError, ValueError) as exc:
                self._journal("state_load_failed", {"error": str(exc)})
        return StreamingStrategy(params), None, None

    def _save(self) -> None:
        if not self.state_file:
            return
        tmp = f"{self.state_file}.tmp"
        with open(tmp, "w") as f:
            json.dump({"strat": self.strat.to_dict(),
                       "day_start_equity": self.day_start_equity,
                       "day": self.day}, f, indent=2)
        os.replace(tmp, self.state_file)

    def _journal(self, event: str, fields: dict) -> None:
        rec = {"ts": dt.datetime.now().isoformat(timespec="seconds"),
               "symbol": self.symbol, "event": event,
               "state": self.strat.state, **fields}
        if self.journal_file:
            with open(self.journal_file, "a") as f:
                f.write(json.dumps(rec) + "\n")
        return rec

    # --------------------------------------------------------- reconcile
    def reconcile(self) -> None:
        """Make the engine agree with the broker's truth about the position."""
        pos = self.broker.position(self.symbol)
        if pos and pos["qty"] > 0 and self.strat.state == "flat":
            self.strat.state = "long"
            self.strat.entry_price = pos["avg_entry_price"]
            self.strat.peak = max(self.strat.peak or 0.0, pos["avg_entry_price"])
            self._journal("reconcile_adopt_long",
                          {"qty": pos["qty"], "avg_entry_price": pos["avg_entry_price"]})
        elif (not pos or pos["qty"] == 0) and self.strat.state == "long":
            # Position vanished underneath us (manual close, prior fill, etc.).
            self.strat.last_exit_price = self.strat.entry_price
            self.strat.state = "flat"
            self.strat.entry_price = None
            self.strat.peak = None
            self._journal("reconcile_flat", {})

    # --------------------------------------------------------- one cycle
    def step(self) -> str:
        if risk.kill_switch_active():
            self._flatten_and_halt("kill switch present")
            return "halt"

        clock = self.broker.clock()
        today = str(clock.get("timestamp", ""))[:10]
        if today and today != self.day:           # new session -> reset loss baseline
            self.day = today
            self.day_start_equity = None

        if not clock.get("is_open"):
            self._journal("market_closed", {})
            return "closed"

        acct = self.broker.account()
        if self.day_start_equity is None:
            self.day_start_equity = acct["equity"]
        if risk.daily_loss_breached(self.day_start_equity, acct["equity"]):
            risk.trip_kill_switch(
                f"daily loss limit: equity {acct['equity']:.2f} "
                f"vs day start {self.day_start_equity:.2f}")
            self._flatten_and_halt("daily loss limit breached")
            return "halt"

        self.reconcile()

        price = self.broker.last_price(self.symbol)
        event = self.strat.update(price)
        if event and event["action"] == "BUY":
            self._do_buy(price, acct)
        elif event and event["action"] == "SELL":
            self._do_sell(price)
        else:
            ref = (self.strat.stop_level if self.strat.state == "long"
                   else self.strat.reentry_trigger)
            self._journal("tick", {"price": price, "ref": ref})

        self._save()
        return "ok"

    # --------------------------------------------------------- order paths
    def _do_buy(self, price: float, acct: dict) -> None:
        qty = risk.entry_qty(acct["cash"], price)
        if qty < 1:
            self._abort_entry("insufficient cash for one share",
                              {"cash": acct["cash"], "price": price})
            return
        try:
            fill = self.broker.buy(self.symbol, qty)
        except BrokerError as exc:
            self._abort_entry("buy rejected", {"error": str(exc)})
            return
        if not fill or fill["filled_qty"] < 1:
            self._abort_entry("buy not filled", {})
            return
        # Anchor the engine to the ACTUAL fill so the stop tracks reality.
        self.strat.entry_price = fill["fill_price"]
        self.strat.peak = fill["fill_price"]
        self._journal("BUY", {"qty": fill["filled_qty"], "fill_price": fill["fill_price"]})

    def _do_sell(self, price: float) -> None:
        try:
            fill = self.broker.close(self.symbol)
        except BrokerError as exc:
            # Couldn't close — re-sync to broker truth next loop; do not lie.
            self._journal("sell_failed", {"error": str(exc)})
            return
        exit_px = fill["fill_price"] if fill else price
        self.strat.last_exit_price = exit_px
        self._journal("SELL", {"fill_price": exit_px})

    def _abort_entry(self, reason: str, fields: dict) -> None:
        # We did not actually take the position the engine just opened — revert.
        self.strat.state = "flat"
        self.strat.entry_price = None
        self.strat.peak = None
        self._journal("skip_buy", {"reason": reason, **fields})

    def _flatten_and_halt(self, reason: str) -> None:
        self.broker.flatten_all()
        self.strat.state = "flat"
        self.strat.entry_price = None
        self.strat.peak = None
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
                          os.environ.get("ALPACA_SECRET_KEY", ""))

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
