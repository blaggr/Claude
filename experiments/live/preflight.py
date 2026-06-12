"""Alpaca paper preflight — one command to verify the whole execution path.

    python experiments/live/preflight.py            # checks only (no orders)
    python experiments/live/preflight.py --order     # also does a 1-share round trip

Paper-only by design: it ignores ALPACA_LIVE and always hits the paper
endpoint, so it can never touch real money. Run the plain form any time; run
--order during US market hours (regular 9:30-16:00 ET, or extended 4:00-9:30 /
16:00-20:00 ET) so the test order can actually fill.
"""
from __future__ import annotations

import argparse
import datetime as dt
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import risk  # noqa: E402
from alpaca import Alpaca, AlpacaError  # noqa: E402

BASKET = ["SPY", "GLD", "USO", "ITA", "FXI"]   # instruments the strategy uses
TEST_SYMBOL = "GLD"                            # cheaper-than-SPY single share


def ok(msg): print(f"  ✓ {msg}")
def bad(msg): print(f"  ✗ {msg}")


def session_now(clock: dict) -> str:
    """'rth' | 'ext' | 'closed' from the Alpaca clock + ET wall time."""
    if clock.get("is_open"):
        return "rth"
    et = dt.datetime.now(dt.timezone.utc) - dt.timedelta(hours=4)  # ~EDT
    if et.weekday() < 5:
        hm = et.hour * 60 + et.minute
        if 4 * 60 <= hm < 9 * 60 + 30 or 16 * 60 <= hm < 20 * 60:
            return "ext"
    return "closed"


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--order", action="store_true",
                    help="place + close a 1-share paper order (needs an open market)")
    args = ap.parse_args(argv)

    print("Alpaca PAPER preflight\n" + "-" * 40)
    fails = 0

    # 1) keys present
    if not (os.environ.get("ALPACA_KEY_ID") and os.environ.get("ALPACA_SECRET_KEY")):
        bad("ALPACA_KEY_ID / ALPACA_SECRET_KEY not set in this shell.")
        print("    export both (from the Alpaca *Paper* dashboard) and re-run.")
        return 1
    ok("API keys present in the environment")

    try:
        b = Alpaca(risk.PAPER_URL)   # paper endpoint, always
    except AlpacaError as e:
        bad(f"client init failed: {e}")
        return 1

    # 2) account
    try:
        acct = b.account()
        status = acct.get("status")
        (ok if status == "ACTIVE" else bad)(f"account status: {status} | equity ${acct['equity']}")
        fails += status != "ACTIVE"
    except AlpacaError as e:
        bad(f"account check failed (bad keys? live keys on paper URL?): {e}")
        return 1

    # 3) clock
    try:
        clock = b.clock()
        sess = session_now(clock)
        ok(f"clock reached — market {'OPEN (regular)' if sess=='rth' else 'closed'}"
           f"{' / extended hours' if sess=='ext' else ''}; next open {clock.get('next_open','?')[:16]}")
    except AlpacaError as e:
        bad(f"clock failed: {e}"); clock, sess = {}, "closed"; fails += 1

    # 4) market data
    for sym in BASKET:
        try:
            ok(f"quote {sym}: ${b.last_price(sym):.2f}")
        except AlpacaError as e:
            bad(f"quote {sym} failed: {e}"); fails += 1

    # 5) optional round-trip order
    if args.order:
        print("-" * 40 + "\nRound-trip test order (paper):")
        if sess == "closed":
            bad("market is closed — skipping the order test. "
                "Re-run --order during 9:30-16:00 ET (or 16:00-20:00 ET extended).")
        else:
            try:
                if sess == "rth":
                    o = b.submit_order(TEST_SYMBOL, 1, "buy", extended_hours=False)
                else:
                    px = b.last_price(TEST_SYMBOL)
                    o = b.submit_order(TEST_SYMBOL, 1, "buy", extended_hours=True,
                                       limit_price=risk.marketable_limit(px, "buy"))
                ok(f"submitted buy 1 {TEST_SYMBOL} (order {o['id'][:8]}…)")
                fill = b.await_fill(o["id"], timeout_s=90)
                if fill:
                    ok(f"filled @ ${float(fill['filled_avg_price']):.2f}")
                    b.close_position(TEST_SYMBOL)
                    ok(f"closed position — check Orders/Positions in the Alpaca dashboard")
                else:
                    bad("order did not fill within 90s (cancelled). Wide spread / thin "
                        "extended-hours book? Try again during regular hours.")
                    fails += 1
            except AlpacaError as e:
                bad(f"order test failed: {e}"); fails += 1

    print("-" * 40)
    if fails == 0:
        print("PASS — Alpaca paper path is working." +
              ("" if args.order else "  Re-run with --order during market hours to test a fill."))
        return 0
    print(f"FAIL — {fails} check(s) failed (see above).")
    return 1


if __name__ == "__main__":
    sys.exit(main())
