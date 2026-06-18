"""Execution surface for the agent — paper by default, never live by accident.

Two interchangeable backends behind one interface so the agent code (and the
tests) never care which is in use:

  * LocalPaperBroker — a self-contained, offline simulated account. Cash +
    positions live in a JSON file under state/. No network, no keys. This is
    what runs in this locked-down environment and in the test suite.

  * AlpacaBroker — wraps the audited REST adapter in experiments/live/alpaca.py
    and routes through experiments/live/risk.py, so it is PAPER unless the
    ALPACA_LIVE=1 env flag AND the acknowledgement file are both present.
    Reaching the live endpoint requires deliberately arming both interlocks.

`get_broker()` picks Alpaca when ALPACA_KEY_ID/SECRET are set, else the local
paper broker. Either way, `mode` is reported up front so the caller (and the
journal) always records whether this was PAPER or LIVE.
"""
from __future__ import annotations

import json
import os
import sys
from dataclasses import dataclass

HERE = os.path.dirname(os.path.abspath(__file__))
STATE_DIR = os.path.join(HERE, "state")
_LIVE = os.path.join(os.path.dirname(HERE), "experiments", "live")


@dataclass
class Fill:
    symbol: str
    side: str            # "buy" | "sell"
    qty: int
    price: float
    status: str          # "filled" | "rejected"
    note: str = ""

    def to_dict(self) -> dict:
        return self.__dict__.copy()


class LocalPaperBroker:
    """Offline simulated brokerage. Deterministic; persists to JSON."""

    def __init__(self, start_cash: float = 10_000.0, state_dir: str = STATE_DIR):
        os.makedirs(state_dir, exist_ok=True)
        self.path = os.path.join(state_dir, "paper_account.json")
        self.mode = "PAPER"
        if os.path.exists(self.path):
            self._s = json.load(open(self.path))
        else:
            self._s = {"cash": float(start_cash), "positions": {}}  # sym -> {qty, avg}
            self._save()

    def _save(self) -> None:
        json.dump(self._s, open(self.path, "w"), indent=2)

    # prices: caller supplies a snapshot dict so the broker stays offline.
    def market_order(self, symbol: str, side: str, qty: int, price: float) -> Fill:
        symbol = symbol.upper()
        qty = int(qty)
        if qty <= 0 or price <= 0:
            return Fill(symbol, side, qty, price, "rejected", "non-positive qty/price")
        pos = self._s["positions"].get(symbol, {"qty": 0, "avg": 0.0})
        cost = qty * price
        if side == "buy":
            if cost > self._s["cash"] + 1e-9:
                return Fill(symbol, side, qty, price, "rejected",
                            f"insufficient cash (need {cost:.2f}, have {self._s['cash']:.2f})")
            new_qty = pos["qty"] + qty
            # weighted average only matters for long adds; shorts track entry too
            pos["avg"] = ((pos["avg"] * pos["qty"]) + cost) / new_qty if new_qty else 0.0
            pos["qty"] = new_qty
            self._s["cash"] -= cost
        else:  # sell (may open/extend a short)
            new_qty = pos["qty"] - qty
            pos["avg"] = pos["avg"] if pos["qty"] > 0 else price
            pos["qty"] = new_qty
            self._s["cash"] += cost
        if pos["qty"] == 0:
            self._s["positions"].pop(symbol, None)
        else:
            self._s["positions"][symbol] = pos
        self._save()
        return Fill(symbol, side, qty, price, "filled")

    def positions(self) -> dict:
        return dict(self._s["positions"])

    def account(self, prices: dict[str, float] | None = None) -> dict:
        prices = prices or {}
        mkt = 0.0
        for sym, pos in self._s["positions"].items():
            px = prices.get(sym, pos["avg"])
            mkt += pos["qty"] * px
        return {"cash": round(self._s["cash"], 2),
                "positions_value": round(mkt, 2),
                "equity": round(self._s["cash"] + mkt, 2),
                "mode": self.mode}


class AlpacaBroker:
    """Live/paper brokerage via the audited REST adapter + risk interlocks."""

    def __init__(self):
        sys.path.insert(0, _LIVE)
        import risk  # noqa: E402
        from alpaca import Alpaca  # noqa: E402
        base, self.mode = risk.resolve_mode()      # PAPER unless interlocks armed
        self._risk = risk
        self.api = Alpaca(base)

    def market_order(self, symbol: str, side: str, qty: int, price: float) -> Fill:
        try:
            clock = self.api.clock()
            ext = not clock.get("is_open", False)
            limit = self._risk.marketable_limit(price, side) if ext else None
            o = self.api.submit_order(symbol.upper(), int(qty), side,
                                      extended_hours=ext, limit_price=limit)
            filled = self.api.await_fill(o["id"])
            if not filled:
                return Fill(symbol, side, qty, price, "rejected", "not filled in time")
            return Fill(symbol, side, int(float(filled["filled_qty"])),
                        float(filled.get("filled_avg_price") or price), "filled")
        except Exception as exc:  # adapter raises AlpacaError; keep the agent alive
            return Fill(symbol, side, qty, price, "rejected", f"{type(exc).__name__}: {exc}")

    def positions(self) -> dict:
        out = {}
        for p in self.api.positions():
            out[p["symbol"]] = {"qty": int(float(p["qty"])), "avg": float(p["avg_entry_price"])}
        return out

    def account(self, prices: dict | None = None) -> dict:
        a = self.api.account()
        return {"cash": float(a["cash"]), "positions_value": float(a.get("long_market_value", 0)),
                "equity": float(a["equity"]), "mode": self.mode}


def get_broker():
    """Alpaca when keys are present (still paper unless interlocks armed),
    otherwise the offline local paper broker."""
    if os.environ.get("ALPACA_KEY_ID") and os.environ.get("ALPACA_SECRET_KEY"):
        try:
            return AlpacaBroker()
        except Exception as exc:
            print(f"[broker] Alpaca init failed ({exc}); using local paper broker")
    return LocalPaperBroker()
