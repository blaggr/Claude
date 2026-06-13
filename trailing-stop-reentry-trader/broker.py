"""Broker interface + a thin Alpaca REST adapter for the trailing-stop trader.

The trader talks to a small ``Broker`` protocol (account / clock / position /
last price / buy / sell-to-flat / flatten), so it can be driven by the live
``AlpacaBroker`` or by an in-memory fake in tests without any network.

``AlpacaBroker`` is a stdlib-only REST client (no SDK) adapted from
``experiments/live/alpaca.py`` so this package stays self-contained — every
request is plain and auditable. Paper and live share the same API; the base URL
is chosen by :mod:`risk`. As defence in depth the live endpoint is refused here
unless ``allow_live=True`` is passed explicitly.
"""
from __future__ import annotations

import json
import time
import urllib.error
import urllib.request
from typing import Optional, Protocol

DATA_URL = "https://data.alpaca.markets"
_LIVE_HOST = "api.alpaca.markets"   # NB: paper host is "paper-api.alpaca.markets"


class BrokerError(RuntimeError):
    def __init__(self, message: str, code: Optional[int] = None):
        super().__init__(message)
        self.code = code


class Broker(Protocol):
    """Everything the trailing-stop trader needs from a broker."""

    def clock(self) -> dict: ...                 # {"is_open": bool, "timestamp": str}
    def account(self) -> dict: ...               # {"equity": float, "cash": float}
    def position(self, symbol: str) -> Optional[dict]: ...  # {"qty","avg_entry_price"} or None
    def last_price(self, symbol: str) -> float: ...
    def buy(self, symbol: str, qty: int, *, extended_hours: bool = False,
            limit_price: Optional[float] = None,
            client_order_id: Optional[str] = None) -> Optional[dict]: ...
    def close(self, symbol: str) -> Optional[dict]: ...  # sell entire position
    def flatten_all(self) -> None: ...


def _fmt_price(p: float) -> str:
    # Alpaca allows sub-penny pricing only below $1; round to 2dp at/above $1.
    return f"{p:.4f}" if p < 1.0 else f"{p:.2f}"


class AlpacaBroker:
    """Live (paper or real) Alpaca REST adapter."""

    def __init__(self, base_url: str, key_id: str, secret: str, *, allow_live: bool = False):
        self.base = base_url.rstrip("/")
        self.key = key_id
        self.secret = secret
        if not (self.key and self.secret):
            raise BrokerError("ALPACA_KEY_ID / ALPACA_SECRET_KEY not set")
        if _LIVE_HOST in self.base and "paper" not in self.base and not allow_live:
            raise BrokerError(
                f"refusing to construct a LIVE broker for {self.base} without allow_live=True")

    # ------------------------------------------------------------- plumbing
    def _req(self, method: str, url: str, body: Optional[dict] = None):
        data = json.dumps(body).encode() if body is not None else None
        req = urllib.request.Request(url, data=data, method=method, headers={
            "APCA-API-KEY-ID": self.key,
            "APCA-API-SECRET-KEY": self.secret,
            "Content-Type": "application/json",
        })
        try:
            with urllib.request.urlopen(req, timeout=30) as r:
                raw = r.read()
                return json.loads(raw) if raw else None
        except urllib.error.HTTPError as e:
            detail = e.read().decode(errors="replace")[:300]
            raise BrokerError(f"{method} {url} -> {e.code}: {detail}", code=e.code) from None

    def _api(self, method: str, path: str, body: Optional[dict] = None):
        return self._req(method, f"{self.base}{path}", body)

    @staticmethod
    def _num(v) -> Optional[float]:
        try:
            return None if v is None else float(v)
        except (TypeError, ValueError):
            return None

    # ------------------------------------------------------------- reads
    def clock(self) -> dict:
        return self._api("GET", "/v2/clock")

    def account(self) -> dict:
        a = self._api("GET", "/v2/account")
        equity, cash = self._num(a.get("equity")), self._num(a.get("cash"))
        if equity is None or cash is None:
            raise BrokerError(f"account has non-numeric balances: "
                              f"equity={a.get('equity')!r} cash={a.get('cash')!r} "
                              f"status={a.get('status')!r}")
        return {"equity": equity, "cash": cash, "status": a.get("status")}

    def position(self, symbol: str) -> Optional[dict]:
        try:
            p = self._api("GET", f"/v2/positions/{symbol}")
        except BrokerError as e:
            if e.code == 404:          # genuine "no open position", by status code
                return None
            raise
        qty, avg = self._num(p.get("qty")), self._num(p.get("avg_entry_price"))
        if qty is None or avg is None:
            raise BrokerError(f"position has non-numeric fields for {symbol}: {p}")
        return {"qty": qty, "avg_entry_price": avg}

    def last_price(self, symbol: str) -> float:
        out = self._req("GET", f"{DATA_URL}/v2/stocks/{symbol}/trades/latest?feed=iex")
        px = self._num((out or {}).get("trade", {}).get("p"))
        if px is None:
            raise BrokerError(f"no last price for {symbol}: {out}")
        return px

    # ------------------------------------------------------------- orders
    def _fill_from(self, o: dict) -> Optional[dict]:
        """Build a fill dict from an order, INCLUDING partial fills. Returns
        None only when nothing at all filled."""
        fq = self._num(o.get("filled_qty")) or 0.0
        avg = self._num(o.get("filled_avg_price"))
        if fq <= 0 or avg is None:
            return None
        return {"filled_qty": fq, "fill_price": avg}

    def _submit(self, symbol: str, qty: int, side: str, *, extended_hours: bool,
                limit_price: Optional[float], client_order_id: Optional[str]) -> dict:
        if int(qty) != qty or qty < 1:
            raise BrokerError(f"invalid order qty {qty!r}: must be a whole number >= 1")
        body = {"symbol": symbol, "qty": str(int(qty)), "side": side,
                "time_in_force": "day", "extended_hours": bool(extended_hours)}
        if extended_hours:
            if limit_price is None:
                raise BrokerError("extended-hours orders must be limit orders")
            body.update(type="limit", limit_price=_fmt_price(limit_price))
        elif limit_price is not None:
            body.update(type="limit", limit_price=_fmt_price(limit_price))
        else:
            body["type"] = "market"
        if client_order_id:
            body["client_order_id"] = client_order_id[:48]
        return self._api("POST", "/v2/orders", body)

    def _await_fill(self, order_id: str, timeout_s: int = 120) -> Optional[dict]:
        """Poll until the order reaches a terminal state, returning whatever
        filled — INCLUDING a partial fill. On timeout, cancel the remainder and
        re-read once to capture any fill the cancel raced with."""
        deadline = time.time() + timeout_s
        while time.time() < deadline:
            o = self._api("GET", f"/v2/orders/{order_id}")
            st = o.get("status")
            if st == "filled":
                return self._fill_from(o)
            if st in ("canceled", "expired", "rejected", "done_for_day"):
                return self._fill_from(o)   # may carry a partial filled_qty
            time.sleep(2)
        # Timed out (or stuck in a non-terminal status like replaced/held):
        # cancel, then re-read so a fill that raced the cancel is not lost.
        try:
            self._api("DELETE", f"/v2/orders/{order_id}")
        except BrokerError:
            pass
        try:
            return self._fill_from(self._api("GET", f"/v2/orders/{order_id}"))
        except BrokerError:
            return None

    def buy(self, symbol: str, qty: int, *, extended_hours: bool = False,
            limit_price: Optional[float] = None,
            client_order_id: Optional[str] = None) -> Optional[dict]:
        o = self._submit(symbol, qty, "buy", extended_hours=extended_hours,
                         limit_price=limit_price, client_order_id=client_order_id)
        return self._await_fill(o["id"])

    def close(self, symbol: str) -> Optional[dict]:
        try:
            o = self._api("DELETE", f"/v2/positions/{symbol}")
        except BrokerError as e:
            if e.code == 404:          # nothing to close, by status code
                return None
            raise
        if o and o.get("id"):
            return self._await_fill(o["id"])
        return None

    def flatten_all(self) -> None:
        try:
            self._api("DELETE", "/v2/positions?cancel_orders=true")
        except BrokerError:
            pass
