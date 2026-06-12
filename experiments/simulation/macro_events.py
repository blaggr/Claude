"""Scheduled macro events (FOMC decisions, CPI releases) for the news sim.

Unlike a Trump post — whose *direction* is in the text — a scheduled release
only has a tradable direction relative to EXPECTATIONS: a rate hold that was
fully priced does nothing; a hot CPI vs consensus sells off. So this module
needs a SURPRISE (actual vs consensus), and that is the one input that is NOT
freely/robustly available (the free economic-calendar scrapes are fragile and
forward coverage is unreliable). Design consequence:

  * The calendar and the surprise -> direction logic are complete and tested.
  * Execution is gated on a SurpriseSource. The default NullSurpriseSource
    returns None, so on an FOMC/CPI day with no feed configured the sim
    ANNOUNCES the event and trades nothing (shadow). Drop a real feed in
    (FileSurpriseSource, or your own implementing get_surprise) and it trades.

Surprise convention: +1 = HAWKISH / HOT (hike-surprise, CPI above consensus),
-1 = DOVISH / COOL. Calibrated leg reactions below are documented average
release-day reactions (direction is well established; magnitudes indicative) —
they are NOT a same-sample event study like the post topics, precisely because
the surprise data to build one wasn't reachable. Treat as priors.
"""
from __future__ import annotations

import datetime as dt
import json
import os
from typing import Protocol

HERE = os.path.dirname(os.path.abspath(__file__))
NY = "America/New_York"

# Scheduled release times (ET). Refresh annually from the official calendars
# (federalreserve.gov FOMC schedule; bls.gov CPI schedule).
FOMC_DATES = {  # decision released ~14:00 ET
    "2025-01-29", "2025-03-19", "2025-05-07", "2025-06-18", "2025-07-30",
    "2025-09-17", "2025-10-29", "2025-12-10",
    "2026-01-28", "2026-03-18", "2026-04-29", "2026-06-17", "2026-07-29",
    "2026-09-16", "2026-11-04", "2026-12-16",
}
CPI_DATES = {  # released 08:30 ET
    "2025-01-15", "2025-02-12", "2025-03-12", "2025-04-10", "2025-05-13",
    "2025-06-11", "2025-07-15", "2025-08-12", "2025-09-11", "2025-10-15",
    "2025-11-13", "2025-12-10",
    "2026-01-13", "2026-02-11", "2026-03-11", "2026-04-10", "2026-05-12",
    "2026-06-10", "2026-07-14", "2026-08-12", "2026-09-11", "2026-10-14",
    "2026-11-12", "2026-12-10",
}
RELEASE_TIME = {"FOMC": (14, 0), "CPI": (8, 30)}

# Leg reaction to a HAWKISH/HOT surprise (sign flips for dovish/cool).
# +1 buy / -1 sell. Documented average release-day reactions.
_REACTION = {
    "FOMC": {
        "SPY": dict(sign=-1, p=0.68, move=0.80, note="hawkish surprise -> equities down"),
        "TLT": dict(sign=-1, p=0.72, move=0.90, note="hawkish -> yields up, long bonds down"),
        "UUP": dict(sign=+1, p=0.66, move=0.40, note="hawkish -> dollar up"),
        "GLD": dict(sign=-1, p=0.60, move=0.60, note="hawkish -> gold down (real-yield up)"),
    },
    "CPI": {
        "SPY": dict(sign=-1, p=0.70, move=0.90, note="hot CPI -> equities down"),
        "TLT": dict(sign=-1, p=0.74, move=0.85, note="hot CPI -> yields up, long bonds down"),
        "UUP": dict(sign=+1, p=0.64, move=0.35, note="hot CPI -> dollar up"),
        "GLD": dict(sign=-1, p=0.58, move=0.55, note="hot CPI -> gold down"),
    },
}
DEFAULT_BASKET = {"FOMC": ["TLT", "SPY", "UUP", "GLD"], "CPI": ["TLT", "SPY", "UUP", "GLD"]}


# ------------------------------------------------------------- surprise feed

class SurpriseSource(Protocol):
    def get_surprise(self, kind: str, date: str) -> float | None:
        """+1 hawkish/hot, -1 dovish/cool, magnitude optional; None if unknown."""


class NullSurpriseSource:
    """Default — no feed wired, so nothing trades (shadow)."""
    def get_surprise(self, kind: str, date: str) -> float | None:
        return None


class FileSurpriseSource:
    """Reads surprises from a JSON file: {"2025-06-11": {"CPI": -1}, ...}.
    Lets you (or a connected feed) drop a number in and have it trade."""
    def __init__(self, path: str | None = None):
        self.path = path or os.path.join(HERE, "macro_surprises.json")

    def get_surprise(self, kind: str, date: str) -> float | None:
        if not os.path.exists(self.path):
            return None
        try:
            data = json.load(open(self.path))
        except Exception:
            return None
        v = data.get(date, {}).get(kind)
        return float(v) if v is not None else None


def default_source() -> SurpriseSource:
    """FileSurpriseSource only if MACRO_SURPRISE_FILE is set; else Null."""
    p = os.environ.get("MACRO_SURPRISE_FILE")
    return FileSurpriseSource(p) if p else NullSurpriseSource()


# ------------------------------------------------------------- event logic

def event_kind(date: str) -> str | None:
    if date in FOMC_DATES:
        return "FOMC"
    if date in CPI_DATES:
        return "CPI"
    return None


def release_timestamp(kind: str, date: str):
    import pandas as pd
    h, m = RELEASE_TIME[kind]
    return pd.Timestamp(f"{date} {h:02d}:{m:02d}", tz=NY)


def plan_for_event(kind: str, surprise: float, edge_qty: float = 100.0) -> dict:
    """Build a directional plan for a known surprise. Legs are signed by
    sign * sign(surprise); weighted by edge ((2p-1)*move). Mirrors the post
    engine's plan shape so the sim/live can reuse the same fill machinery."""
    s = 1 if surprise > 0 else -1
    table = _REACTION[kind]
    raw = []
    for ins in DEFAULT_BASKET[kind]:
        c = table[ins]
        exp_sign = c["sign"] * s
        edge = (2 * c["p"] - 1) * c["move"]
        raw.append((ins, c, exp_sign, edge))
    total = sum(e for *_, e in raw) or 1.0
    legs = []
    for ins, c, exp_sign, edge in raw:
        legs.append({
            "instrument": ins, "side": "BUY" if exp_sign > 0 else "SELL",
            "weight": round(edge / total, 4),
            "probability": c["p"],
            "expected_move_pct": round(c["move"] * (1 if exp_sign > 0 else -1), 2),
        })
    legs.sort(key=lambda l: -abs(l["expected_move_pct"]) * l["probability"])
    label = "hawkish/hot" if s > 0 else "dovish/cool"
    return {"kind": kind, "surprise": s, "label": label, "legs": legs}


def check_today(today: str, source: SurpriseSource | None = None) -> dict | None:
    """Returns None if no macro event today; otherwise a dict describing the
    event and (if a surprise is known) the directional plan. status is
    'traded-ready' (surprise present) or 'shadow' (no feed)."""
    kind = event_kind(today)
    if not kind:
        return None
    source = source or default_source()
    surprise = source.get_surprise(kind, today)
    if surprise is None:
        return {"kind": kind, "status": "shadow",
                "note": f"{kind} scheduled today ({RELEASE_TIME[kind][0]:02d}:"
                        f"{RELEASE_TIME[kind][1]:02d} ET) — no surprise feed configured, "
                        "not traded. Wire a consensus+actual feed to enable."}
    plan = plan_for_event(kind, surprise)
    return {"kind": kind, "status": "traded-ready", "surprise": surprise,
            "release_ts": str(release_timestamp(kind, today)), **plan}
