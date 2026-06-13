"""Risk interlocks for the Alpaca trailing-stop trader.

Adapted from ``experiments/live/risk.py`` and pared down to this single-symbol,
all-in / all-out strategy:

  * PAPER BY DEFAULT.   Live needs BOTH ``ALPACA_LIVE=1`` AND a file
                        ``LIVE_TRADING_ENABLED`` next to this module whose
                        stripped contents EQUAL the acknowledgement line.
  * KILL SWITCH.        A file named ``KILL`` -> flatten and halt.
  * DAILY LOSS LIMIT.   Equity at/below MAX_DAILY_LOSS_PCT under the day's
                        starting equity -> flatten, write KILL, halt.
  * TOTAL DRAWDOWN.     Equity at/below MAX_TOTAL_DRAWDOWN_PCT under the highest
                        equity ever seen -> flatten, write KILL, halt. This
                        catches a slow multi-day bleed that the per-day limit,
                        which re-anchors each session, would miss.
  * SINGLE POSITION.    All-in / all-out; entry size is a fraction of *cash*
                        (never margin, budget clamped to [0,100]%).

All numeric inputs are validated to be FINITE — a NaN/inf slipping in must never
silently disable a limit (e.g. `eq <= nan` is always False).
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
    """Parse a FINITE float env var, else fall back with a warning (instead of
    crashing import, or accepting 'nan'/'inf' which would disable a limit)."""
    raw = os.environ.get(name)
    if raw is None:
        return default
    try:
        v = float(raw)
    except ValueError:
        print(f"[risk] {name}={raw!r} is not a number; using default {default}")
        return default
    if not math.isfinite(v):
        print(f"[risk] {name}={raw!r} is not finite; using default {default}")
        return default
    return v


BUDGET_PCT = _env_float("BUDGET_PCT", 95.0)
MAX_DAILY_LOSS_PCT = _env_float("MAX_DAILY_LOSS_PCT", 5.0)
MAX_TOTAL_DRAWDOWN_PCT = _env_float("MAX_TOTAL_DRAWDOWN_PCT", 15.0)


def _finite(*vals) -> bool:
    try:
        return all(math.isfinite(float(v)) for v in vals)
    except (TypeError, ValueError):
        return False


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
    positive, finite baseline and finite equity; otherwise there is no usable
    line and we do not (falsely) report a breach."""
    if not _finite(day_start_equity, equity):
        return False
    base, eq = float(day_start_equity), float(equity)
    if base <= 0:
        return False
    return eq <= base * (1 - MAX_DAILY_LOSS_PCT / 100.0)


def total_drawdown_breached(peak_equity, equity) -> bool:
    """True when equity has fallen MAX_TOTAL_DRAWDOWN_PCT below the high-water
    equity. Catches a sustained multi-day bleed the daily limit re-anchors past."""
    if not _finite(peak_equity, equity):
        return False
    peak, eq = float(peak_equity), float(equity)
    if peak <= 0:
        return False
    return eq <= peak * (1 - MAX_TOTAL_DRAWDOWN_PCT / 100.0)


def entry_qty(cash: float, price: float, budget_pct: float = None) -> int:
    """Whole-share size for an all-in long: a fraction of CASH (never margin).
    budget_pct is clamped to [0, 100]. Returns 0 on any non-finite or
    non-positive input, or when the budget can't afford one share."""
    pct = BUDGET_PCT if budget_pct is None else budget_pct
    if not _finite(cash, price, pct):
        return 0
    pct = max(0.0, min(100.0, pct))
    if price <= 0 or cash <= 0:
        return 0
    return int(math.floor(cash * pct / 100.0 / price))
