"""Live *paper* trading loop — simulated fills only, never real orders.

Polls the latest price for a ticker on an interval and runs the same
trailing-stop / re-entry rule tick-by-tick. Every simulated BUY/SELL is
appended to a trade log and the engine state is persisted to a JSON file so
you can stop and resume without losing the position.

Example::

    python paper.py --ticker SPY --trail 1.5 --reentry 1 --poll 60

Stop it any time with Ctrl-C. Nothing here connects to a brokerage or moves
real money — it is a dry run you can leave running to watch the rule fire.
"""
from __future__ import annotations

import argparse
import csv
import datetime as dt
import json
import os
import signal
import sys
import time

import data as data_mod
from strategy import StrategyParams, StreamingStrategy

_running = True


def _stop(signum, frame):  # pragma: no cover - signal handler
    global _running
    _running = False
    print("\nStopping paper loop (state saved)...")


def load_state(path: str, params: StrategyParams) -> StreamingStrategy:
    if path and os.path.exists(path):
        try:
            with open(path) as f:
                return StreamingStrategy.from_dict(json.load(f))
        except (json.JSONDecodeError, KeyError, TypeError, ValueError) as exc:
            print(f"  warning: could not read state file '{path}' ({exc}); "
                  "starting from a fresh position.")
    return StreamingStrategy(params)


def save_state(path: str, strat: StreamingStrategy) -> None:
    if not path:
        return
    # Write to a temp file and atomically replace, so a crash mid-write cannot
    # truncate the existing good state to an empty/partial file.
    tmp = f"{path}.tmp"
    with open(tmp, "w") as f:
        json.dump(strat.to_dict(), f, indent=2)
    os.replace(tmp, path)


def log_fill(path: str, ticker: str, event: dict) -> None:
    if not path:
        return
    new = not os.path.exists(path)
    with open(path, "a", newline="") as f:
        w = csv.writer(f)
        if new:
            w.writerow(["timestamp", "ticker", "action", "price", "return_pct"])
        w.writerow([
            dt.datetime.now().isoformat(timespec="seconds"),
            ticker,
            event["action"],
            f"{event['price']:.4f}",
            f"{event.get('return_pct', ''):}",
        ])


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--ticker", required=True, help="Symbol to paper-trade, e.g. SPY")
    p.add_argument("--trail", type=float, default=1.0, help="Trailing stop distance in $ (default 1.0)")
    p.add_argument("--reentry", type=float, default=1.0, help="Re-entry trigger in $ above last exit (default 1.0)")
    p.add_argument("--poll", type=float, default=60.0, help="Seconds between price polls (default 60)")
    p.add_argument("--iterations", type=int, default=0, help="Stop after N polls (0 = run until Ctrl-C)")
    p.add_argument("--no-start-entry", action="store_true", help="Wait for a re-entry trigger instead of buying immediately")
    p.add_argument("--state-file", default="paper_state.json", help="Where to persist engine state")
    p.add_argument("--log-file", default="paper_trades.csv", help="Where to append simulated fills")
    return p


def main(argv=None) -> int:
    global _running
    _running = True  # reset so re-invocation in the same process actually runs
    args = build_parser().parse_args(argv)
    signal.signal(signal.SIGINT, _stop)

    params = StrategyParams(
        trail=args.trail, reentry=args.reentry,
        enter_at_start=not args.no_start_entry,
    )
    strat = load_state(args.state_file, params)
    # Only adopt CLI params when flat. Overwriting the params of an OPEN
    # position would silently move its stop (e.g. resuming without re-passing
    # --trail would reset the trail to the default and shift the live stop).
    if strat.state == "flat":
        strat.params = params
    elif (strat.params.trail, strat.params.reentry) != (params.trail, params.reentry):
        print(f"  note: resuming an OPEN position; keeping its saved params "
              f"(trail ${strat.params.trail:g}, reentry +${strat.params.reentry:g}). "
              "CLI trail/reentry are ignored until the position closes.")

    print(f"Paper trading {args.ticker}  (trail ${params.trail:g}, re-entry +${params.reentry:g})")
    print(f"Polling every {args.poll:g}s — simulated fills only, no real orders. Ctrl-C to stop.\n")

    i = 0
    consecutive_failures = 0
    max_failures = 5
    while _running:
        i += 1
        try:
            price = data_mod.latest_price(args.ticker)
            consecutive_failures = 0
        except Exception as exc:
            consecutive_failures += 1
            print(f"  [{dt.datetime.now():%H:%M:%S}] price fetch failed "
                  f"({consecutive_failures}/{max_failures}): {exc}")
            if consecutive_failures >= max_failures:
                print("  giving up after repeated price-fetch failures "
                      "(check the ticker symbol / network).")
                break
            if args.iterations and i >= args.iterations:
                break
            _sleep(args.poll)
            continue

        event = strat.update(price)
        stamp = dt.datetime.now().strftime("%H:%M:%S")
        if event:
            save_state(args.state_file, strat)
            log_fill(args.log_file, args.ticker, event)
            extra = f"  (+{event['return_pct']*100:.2f}%)" if "return_pct" in event else ""
            print(f"  [{stamp}] {event['action']:4s} @ {price:.2f}{extra}")
        else:
            ref = strat.stop_level if strat.state == "long" else strat.reentry_trigger
            ref_lbl = "stop" if strat.state == "long" else "re-entry"
            ref_txt = f"{ref:.2f}" if ref is not None else "—"
            print(f"  [{stamp}] {strat.state:4s}  price {price:.2f}   {ref_lbl} {ref_txt}")
            save_state(args.state_file, strat)

        if args.iterations and i >= args.iterations:
            break
        _sleep(args.poll)

    print("Done.")
    return 0


def _sleep(seconds: float) -> None:
    # responsive sleep so Ctrl-C is honored promptly
    end = time.time() + seconds
    while _running and time.time() < end:
        time.sleep(min(0.5, end - time.time()))


if __name__ == "__main__":
    sys.exit(main())
