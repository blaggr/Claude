"""Phase-1 macro source: load release Events from a CSV (ts,type,symbol).

Phase 1 needs only release TIMESTAMPS (the drift signal reacts to price, not to
the actual/consensus). Wiring real BLS/Fed calendars + ALFRED actuals is a
follow-on; this ingests a curated CSV so the backtest is fully testable offline.
"""
from __future__ import annotations
import csv
import datetime as dt
from events import Event


def load_events(path: str) -> list[Event]:
    out: list[Event] = []
    with open(path) as f:
        for i, row in enumerate(csv.DictReader(f), start=2):
            try:
                ts = dt.datetime.fromisoformat(row["ts"].replace("Z", "+00:00"))
            except (KeyError, ValueError, AttributeError) as exc:
                raise ValueError(f"{path} line {i}: bad ts {row.get('ts')!r}: {exc}") from None
            if ts.tzinfo is None:
                raise ValueError(f"{path} line {i}: ts must be tz-aware")
            out.append(Event(ts=ts, source="macro", type=row["type"],
                             payload={"symbol": row["symbol"]}))
    return sorted(out, key=lambda e: e.ts)
