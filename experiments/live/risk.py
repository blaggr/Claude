"""Risk interlocks and position sizing for the live trader.

These are the controls I would not run real money without:

  * PAPER BY DEFAULT.   Live needs BOTH the env var ALPACA_LIVE=1 AND a file
                        LIVE_TRADING_ENABLED next to this module containing
                        the exact acknowledgement line below. Either alone
                        refuses to start. Deleting the file is the permanent
                        off switch.
  * KILL SWITCH.        Touch a file named KILL in this directory -> the
                        worker flattens every position and halts.
  * DAILY LOSS LIMIT.   Equity dropping MAX_DAILY_LOSS_PCT below the day's
                        starting equity -> flatten everything, write KILL,
                        halt. A human must remove KILL to resume.
  * PER-EVENT BUDGET.   At most EVENT_BUDGET_PCT of current equity is
                        committed to one news event, split across legs by
                        edge weight, whole shares only, never on margin
                        beyond shorting the SELL legs.
  * ONE EVENT AT A TIME and idempotent client_order_ids (post id + leg), so
                        a crashed-and-restarted worker cannot double-order.
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

EVENT_BUDGET_PCT = float(os.environ.get("EVENT_BUDGET_PCT", "25"))      # % of equity per event
MAX_DAILY_LOSS_PCT = float(os.environ.get("MAX_DAILY_LOSS_PCT", "5"))   # % from day start -> kill
LIMIT_BUFFER = 0.002   # marketable-limit buffer for extended-hours fills


def resolve_mode() -> tuple[str, str]:
    """Return (base_url, mode). Live requires env flag + acknowledgement file."""
    want_live = os.environ.get("ALPACA_LIVE") == "1"
    ack = os.path.exists(ACK_FILE) and ACK_TEXT in open(ACK_FILE).read()
    if want_live and ack:
        return LIVE_URL, "LIVE"
    if want_live and not ack:
        raise SystemExit(
            "ALPACA_LIVE=1 is set but the acknowledgement file is missing.\n"
            f"To trade real money, create {ACK_FILE} containing exactly:\n"
            f"  {ACK_TEXT}\n"
            "Refusing to start."
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
    return equity < day_start_equity * (1 - MAX_DAILY_LOSS_PCT / 100.0)


def size_legs(legs: list[dict], prices: dict[str, float], equity: float) -> list[dict]:
    """Whole-share sizing: weight * (EVENT_BUDGET_PCT% of equity) per leg.
    Legs that round to zero shares are dropped (logged by the caller)."""
    budget = equity * EVENT_BUDGET_PCT / 100.0
    out = []
    for leg in legs:
        p = prices.get(leg["instrument"])
        if not p or p <= 0:
            continue
        qty = math.floor(leg["weight"] * budget / p)
        if qty >= 1:
            out.append({**leg, "qty": qty, "ref_price": p})
    return out


def marketable_limit(price: float, side: str) -> float:
    """Aggressive-but-bounded limit for extended-hours entries/exits."""
    return round(price * (1 + LIMIT_BUFFER), 2) if side == "buy" else round(price * (1 - LIMIT_BUFFER), 2)
