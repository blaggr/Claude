"""Risk interlocks for the Alpaca trailing-stop trader.

The controls I would not leave a trader running without — adapted from
``experiments/live/risk.py`` and pared down to this single-symbol, all-in /
all-out strategy:

  * PAPER BY DEFAULT.   Live needs BOTH ``ALPACA_LIVE=1`` AND a file
                        ``LIVE_TRADING_ENABLED`` next to this module containing
                        the exact acknowledgement line. Either alone refuses to
                        start. Deleting the file is the permanent off switch.
  * KILL SWITCH.        A file named ``KILL`` in this directory -> flatten the
                        position and halt. A human must remove it to resume.
  * DAILY LOSS LIMIT.   Equity dropping MAX_DAILY_LOSS_PCT below the day's
                        starting equity -> flatten, write KILL, halt.
  * SINGLE POSITION.    The strategy is all-in / all-out in one symbol; entry
                        size is a fraction of *cash* (never margin) so a
                        restart cannot stack leverage.
"""
from __future__ import annotations

import math
import os

HERE = os.path.dirname(os.path.abspath(__file__))
PAPER_URL = "https://paper-api.alpaca.markets"
LIVE_URL = "https://api.alpaca.markets"
ACK_FILE = os.path.join(HERE, "LIVE_TRADING_ENABLED")
KILL_FILE = os.path.join(HERE, "KILL")
ACK_TEXT = "I UNDERSTAND THIS PLACES REAL ORDERS WITH REAL MONEY"

BUDGET_PCT = float(os.environ.get("BUDGET_PCT", "95"))          # % of cash per entry
MAX_DAILY_LOSS_PCT = float(os.environ.get("MAX_DAILY_LOSS_PCT", "5"))  # % from day start -> kill


def resolve_mode() -> tuple[str, str]:
    """Return (base_url, mode). Live requires the env flag AND the ack file."""
    want_live = os.environ.get("ALPACA_LIVE") == "1"
    ack = os.path.exists(ACK_FILE) and ACK_TEXT in open(ACK_FILE).read()
    if want_live and ack:
        return LIVE_URL, "LIVE"
    if want_live and not ack:
        raise SystemExit(
            "ALPACA_LIVE=1 is set but the acknowledgement file is missing.\n"
            f"To trade real money, create {ACK_FILE} containing exactly:\n"
            f"  {ACK_TEXT}\nRefusing to start."
        )
    if ack and not want_live:
        print("[risk] acknowledgement file present but ALPACA_LIVE!=1 — running PAPER")
    return PAPER_URL, "PAPER"


def kill_switch_active() -> bool:
    return os.path.exists(KILL_FILE)


def trip_kill_switch(reason: str) -> None:
    with open(KILL_FILE, "w") as f:
        f.write(reason + "\n")


def daily_loss_breached(day_start_equity: float, equity: float) -> bool:
    if not day_start_equity:
        return False
    return equity < day_start_equity * (1 - MAX_DAILY_LOSS_PCT / 100.0)


def entry_qty(cash: float, price: float, budget_pct: float = BUDGET_PCT) -> int:
    """Whole-share size for an all-in long: a fraction of CASH (never margin).
    Returns 0 when the budget can't afford a single share (logged by caller)."""
    if price <= 0 or cash <= 0:
        return 0
    return int(math.floor(cash * budget_pct / 100.0 / price))
