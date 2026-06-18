"""Structured store of open positions and their exit plans.

The broker knows *what* you hold; this knows *why* and *until when* — the exit
metadata the agent needs to manage a position after it is opened: which side and
size, the entry price/time, the calibrated exit window, the trailing-stop
distance, the hard boundary timestamp, and the running peak/trough the trailing
stop ratchets against.

One record per symbol (the agent trades one event per instrument at a time),
persisted to state/open_positions.json so exits survive a restart. Pure local
state — no broker, no network.
"""
from __future__ import annotations

import json
import os

HERE = os.path.dirname(os.path.abspath(__file__))
DEFAULT_DIR = os.path.join(HERE, "state")


class OpenPositions:
    def __init__(self, state_dir: str = DEFAULT_DIR):
        os.makedirs(state_dir, exist_ok=True)
        self.path = os.path.join(state_dir, "open_positions.json")
        self._p: dict[str, dict] = {}
        if os.path.exists(self.path):
            try:
                self._p = json.load(open(self.path))
            except Exception:
                self._p = {}

    def _save(self) -> None:
        json.dump(self._p, open(self.path, "w"), indent=2, default=str)

    def all(self) -> dict[str, dict]:
        return dict(self._p)

    def get(self, symbol: str) -> dict | None:
        return self._p.get(symbol.upper())

    def record(self, symbol: str, *, side: str, qty: int, entry_price: float,
               entry_ts: str, window: str, trail_pct: float, boundary: str,
               headline: str = "") -> dict:
        """Open (or replace) the tracked position for ``symbol``. ``side`` is the
        ENTRY order side ('BUY' opens a long, 'SELL' opens a short)."""
        rec = {"side": side.upper(), "qty": int(qty), "entry_price": float(entry_price),
               "entry_ts": entry_ts, "window": window, "trail_pct": float(trail_pct),
               "boundary": boundary, "best": float(entry_price),
               "headline": headline[:160]}
        self._p[symbol.upper()] = rec
        self._save()
        return rec

    def update_best(self, symbol: str, best: float) -> None:
        r = self._p.get(symbol.upper())
        if r is not None:
            r["best"] = float(best)
            self._save()

    def remove(self, symbol: str) -> None:
        if self._p.pop(symbol.upper(), None) is not None:
            self._save()
