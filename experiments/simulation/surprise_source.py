"""Consensus/surprise data sources for scheduled macro events (CPI / FOMC).

This module is a PANDAS-FREE, pure-stdlib companion to ``macro_events.py``. It
provides concrete ``SurpriseSource`` implementations that turn a *consensus* and
an *actual* print into the single number ``macro_events`` consumes.

Interface mirrored from ``macro_events.py`` (the runtime protocol)::

    class SurpriseSource(Protocol):
        def get_surprise(self, kind: str, date: str) -> float | None:
            '''+1 hawkish/hot, -1 dovish/cool, magnitude optional; None if unknown.'''

So a source MUST expose ``get_surprise(kind, date)`` returning:
  * a ``float`` whose SIGN encodes direction (+1 hawkish/hot, -1 dovish/cool)
    and whose MAGNITUDE is an optional, normalized strength (>= 0 in absolute
    value); ``macro_events.plan_for_event`` only looks at ``surprise > 0`` for
    the sign today, but downstream code can use the magnitude to size, and
  * ``None`` when the surprise is unknown for that (kind, date) -> the sim
    stays in "shadow" mode and trades nothing, exactly like today.

``kind`` is ``"FOMC"`` or ``"CPI"``; ``date`` is an ISO ``"YYYY-MM-DD"`` string.

--------------------------------------------------------------------------------
Sign convention (the crucial bit)
--------------------------------------------------------------------------------
The raw difference ``actual - consensus`` does NOT always map to "+1 = hawkish"
the same way across event types, so each event type carries an orientation:

  * CPI  : a HOTTER print (actual > consensus) is HAWKISH  -> +1.
           orientation = +1, surprise_sign = sign(actual - consensus).
  * FOMC : higher policy rate / hawkish dots vs consensus is HAWKISH -> +1.
           orientation = +1, surprise_sign = sign(actual - consensus).

(If you ever add an "inverted" series, e.g. an unemployment-rate surprise where
HIGHER is DOVISH, set its orientation to -1 in ``EVENT_ORIENTATION``.)

The normalized MAGNITUDE is ``abs(actual - consensus) / scale`` where ``scale``
is a per-event-type, roughly one-"surprising"-print denominator so the number
lands near 1.0 for a typical surprise. Scales are indicative priors, not a
calibrated event study (the consensus history to build one is paid data).

--------------------------------------------------------------------------------
Sample surprise file schema (JSON)
--------------------------------------------------------------------------------
Point ``MACRO_SURPRISE_FILE`` at a JSON file. Two shapes are accepted:

1. Rich shape (preferred) — keyed by date, then by event kind, each holding the
   consensus + actual prints (and optional pre-normalized sign/magnitude)::

       {
         "2025-06-11": {
           "CPI":  {"consensus": 3.2, "actual": 3.5, "unit": "yoy_pct"},
           "FOMC": {"consensus": 5.25, "actual": 5.50}
         },
         "2025-05-13": {
           "CPI":  {"consensus": 3.4, "actual": 3.1}
         }
       }

   ``actual - consensus`` is computed and normalized here.

2. Terse shape (back-compatible with the inline FileSurpriseSource in
   macro_events.py) — keyed by date, then kind, holding the surprise directly::

       {"2025-06-11": {"CPI": 1.0}, "2025-05-13": {"CPI": -0.5}}

CSV is also supported (stdlib ``csv`` module). Columns::

       date,kind,consensus,actual          # rich
   or  date,kind,surprise                  # terse
       2025-06-11,CPI,3.2,3.5
       2025-05-13,CPI,,,-0.5               # (terse rows use the surprise col)

A row with ``consensus`` and ``actual`` is treated as rich; a row with only
``surprise`` is terse.

--------------------------------------------------------------------------------
Where the real (consensus) data comes from
--------------------------------------------------------------------------------
Forward-looking consensus is the input that is NOT freely/robustly available.
Realistic options, mostly paid:

  * Bloomberg (ECO <GO> / BLP API), Refinitiv/LSEG Eikon, Haver Analytics,
    Econoday, MarketWatch/Investing.com economic calendars (scrapes are
    fragile), TradingEconomics API, FRED (actuals only, NO consensus).

Populate the file by, ahead of each release, recording the median analyst
consensus, then after the print recording the actual; or have an automated feed
write the rich JSON/CSV above. With nothing configured, the sim shadows.
"""
from __future__ import annotations

import csv
import datetime as _dt  # noqa: F401  (kept for callers/type clarity)
import json
import os
from typing import Optional, Protocol


# Orientation: does "actual > consensus" mean HAWKISH (+1) or DOVISH (-1)?
EVENT_ORIENTATION = {
    "FOMC": +1,   # higher rate / hawkish vs consensus -> hawkish
    "CPI": +1,    # hotter inflation vs consensus -> hawkish
}

# Indicative per-event normalization scales so a "typical" surprise ~= 1.0.
# CPI in YoY percentage points: a 0.2pp miss is already a big surprise.
# FOMC in policy-rate percentage points: a 0.25 (one click) surprise is huge.
EVENT_SCALE = {
    "FOMC": 0.25,
    "CPI": 0.2,
}

# Cap the normalized magnitude so a data-entry typo can't size a monster trade.
_MAX_MAGNITUDE = 5.0


class SurpriseSource(Protocol):
    """Structural type matching macro_events.SurpriseSource exactly."""

    def get_surprise(self, kind: str, date: str) -> Optional[float]:
        """+1 hawkish/hot, -1 dovish/cool, magnitude optional; None if unknown."""
        ...


def compute_surprise(kind: str, consensus: float, actual: float) -> float:
    """Turn a consensus + actual into the signed, normalized surprise.

    Returns ``orientation * sign(actual - consensus) * normalized_magnitude``.
    A zero difference returns ``0.0`` (no surprise, no trade direction).
    """
    orientation = EVENT_ORIENTATION.get(kind, +1)
    scale = EVENT_SCALE.get(kind, 1.0) or 1.0
    diff = float(actual) - float(consensus)
    if diff == 0:
        return 0.0
    sign = 1.0 if diff > 0 else -1.0
    magnitude = min(abs(diff) / scale, _MAX_MAGNITUDE)
    return orientation * sign * magnitude


def _coerce_entry(kind: str, entry) -> Optional[float]:
    """Normalize one (kind -> value) entry from a loaded record into a surprise.

    Accepts the terse form (a bare number) or the rich form (a dict with
    consensus + actual, or a pre-computed surprise/sign/magnitude). Returns
    None if the entry is missing or unusable.
    """
    if entry is None:
        return None
    # Terse: a bare number.
    if isinstance(entry, bool):
        return None
    if isinstance(entry, (int, float)):
        return float(entry)
    if isinstance(entry, str):
        try:
            return float(entry)
        except ValueError:
            return None
    if isinstance(entry, dict):
        # Pre-computed surprise wins if present.
        if entry.get("surprise") is not None:
            try:
                return float(entry["surprise"])
            except (TypeError, ValueError):
                return None
        cons = entry.get("consensus")
        act = entry.get("actual")
        if cons is not None and act is not None:
            try:
                return compute_surprise(kind, float(cons), float(act))
            except (TypeError, ValueError):
                return None
        # A pre-computed sign (+magnitude) without prints.
        if entry.get("sign") is not None:
            try:
                sign = float(entry["sign"])
                mag = float(entry.get("magnitude", 1.0))
                return (1.0 if sign > 0 else -1.0 if sign < 0 else 0.0) * abs(mag)
            except (TypeError, ValueError):
                return None
    return None


class ManualSurpriseSource:
    """In-memory source for tests / ad-hoc use.

    Construct from a dict keyed by date then kind, in either the rich or terse
    shape (see module docstring)::

        ManualSurpriseSource({"2025-06-11": {"CPI": {"consensus": 3.2, "actual": 3.5}}})
        ManualSurpriseSource({"2025-06-11": {"CPI": 1.0}})
    """

    def __init__(self, data: Optional[dict] = None):
        self.data = dict(data or {})

    def get_surprise(self, kind: str, date: str) -> Optional[float]:
        entry = self.data.get(date, {})
        if not isinstance(entry, dict):
            return None
        return _coerce_entry(kind, entry.get(kind))


class FileSurpriseSource:
    """Reads consensus+actual (or a pre-computed surprise) from JSON or CSV.

    Path defaults to ``$MACRO_SURPRISE_FILE``, then to ``macro_surprises.json``
    next to this module. Missing file or missing entry -> ``None`` (shadow),
    never raises. The file format is auto-detected from the extension; ``.csv``
    is parsed with the stdlib ``csv`` module, anything else is parsed as JSON.
    """

    def __init__(self, path: Optional[str] = None):
        if path is None:
            path = os.environ.get("MACRO_SURPRISE_FILE")
        if path is None:
            here = os.path.dirname(os.path.abspath(__file__))
            path = os.path.join(here, "macro_surprises.json")
        self.path = path

    # -- loading -----------------------------------------------------------
    def _load(self) -> dict:
        """Load the file into the nested ``{date: {kind: entry}}`` shape.

        Returns an empty dict on any failure (missing file, parse error) so
        ``get_surprise`` degrades to shadow rather than raising.
        """
        if not self.path or not os.path.exists(self.path):
            return {}
        try:
            if self.path.lower().endswith(".csv"):
                return self._load_csv()
            return self._load_json()
        except Exception:
            return {}

    def _load_json(self) -> dict:
        with open(self.path, "r", encoding="utf-8") as fh:
            data = json.load(fh)
        return data if isinstance(data, dict) else {}

    def _load_csv(self) -> dict:
        out: dict = {}
        with open(self.path, "r", encoding="utf-8", newline="") as fh:
            reader = csv.DictReader(fh)
            for row in reader:
                if not row:
                    continue
                date = (row.get("date") or "").strip()
                kind = (row.get("kind") or "").strip()
                if not date or not kind:
                    continue
                cons = (row.get("consensus") or "").strip()
                act = (row.get("actual") or "").strip()
                surp = (row.get("surprise") or "").strip()
                if cons != "" and act != "":
                    entry = {"consensus": float(cons), "actual": float(act)}
                elif surp != "":
                    entry = {"surprise": float(surp)}
                else:
                    continue
                out.setdefault(date, {})[kind] = entry
        return out

    # -- interface ---------------------------------------------------------
    def get_surprise(self, kind: str, date: str) -> Optional[float]:
        data = self._load()
        entry = data.get(date, {})
        if not isinstance(entry, dict):
            return None
        return _coerce_entry(kind, entry.get(kind))


def default_source() -> SurpriseSource:
    """Mirror of macro_events.default_source: FileSurpriseSource only if
    MACRO_SURPRISE_FILE is set, else a do-nothing source (None -> shadow)."""
    path = os.environ.get("MACRO_SURPRISE_FILE")
    if path:
        return FileSurpriseSource(path)
    return ManualSurpriseSource({})
