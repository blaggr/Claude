"""Risk interlocks for the Alpaca trailing-stop trader.

The controls I would not leave a trader running without — adapted from
``experiments/live/risk.py`` and pared down to this single-symbol, all-in /
all-out strategy:

  * PAPER BY DEFAULT.   Live needs BOTH ``ALPACA_LIVE=1`` AND a file
                        ``LIVE_TRADING_ENABLED`` next to this module whose
                        contents are EXACTLY the acknowledgement line (after
                        stripping surrounding whitespace). Either alone refuses
                        to start. Deleting the file is the permanent off switch.
  * KILL SWITCH.        A file named ``KILL`` in this directory -> flatten the
                        position and halt. A human must remove it to resume.
  * DAILY LOSS LIMIT.   Equity at or below MAX_DAILY_LOSS_PCT under the day's
                        starting equity -> flatten, write KILL, halt.
  * SINGLE POSITION.    The strategy is all-in / all-out in one symbol; entry
                        size is a fraction of *cash* (never margin, budget
                        clamped to <=100%) so a restart cannot stack leverage.
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


def _env_float(name: str, default: float) -> float:
    """Parse a float env var, falling back (with a warning) instead of crashing
    the whole risk module at import on a stray '%' or space."""
    raw = os.environ.get(name)
    if raw is None:
        return default
    try:
        return float(raw)
    except ValueError:
        print(f"[risk] {name}={raw!r} is not a number; using default {default}")
        return default


BUDGET_PCT = _env_float("BUDGET_PCT", 95.0)            # % of cash per entry
MAX_DAILY_LOSS_PCT = _env_float("MAX_DAILY_LOSS_PCT", 5.0)  # % from day start -> kill


def resolve_mode() -> tuple[str, str]:
    """Return (base_url, mode). Live requires the env flag AND an ack file whose
    stripped contents equal the acknowledgement line EXACTLY."""
    want_live = os.environ.get("ALPACA_LIVE") == "1"
    ack = False
    if os.path.exists(ACK_FILE):
        try:
            ack = open(ACK_FILE).read().strip() == ACK_TEXT
        except OSError:
            ack = False
    if want_live and ack:
        return LIVE_URL, "LIVE"
    if want_live and not ack:
        raise SystemExit(
            "ALPACA_LIVE=1 is set but the acknowledgement file is missing or not exact.\n"
            f"To trade real money, create {ACK_FILE} containing EXACTLY this line:\n"
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


def daily_loss_breached(day_start_equity, equity) -> bool:
    """True when equity has fallen to/through the daily loss line. Requires a
    POSITIVE baseline; a missing/zero/negative baseline is not a usable line."""
    try:
        base = float(day_start_equity)
        eq = float(equity)
    except (TypeError, ValueError):
        return False
    if base <= 0:
        return False
    return eq <= base * (1 - MAX_DAILY_LOSS_PCT / 100.0)


def entry_qty(cash: float, price: float, budget_pct: float = None) -> int:
    """Whole-share size for an all-in long: a fraction of CASH (never margin).
    budget_pct is clamped to [0, 100] so it can never size beyond cash.
    Returns 0 when the budget can't afford one share (logged by caller)."""
    pct = BUDGET_PCT if budget_pct is None else budget_pct
    pct = max(0.0, min(100.0, pct))
    if price <= 0 or cash <= 0:
        return 0
    return int(math.floor(cash * pct / 100.0 / price))
