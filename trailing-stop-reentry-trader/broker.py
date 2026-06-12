"""Broker interface + a thin Alpaca REST adapter for the trailing-stop trader.

The trader talks to a small ``Broker`` protocol (account / clock / position /
last price / buy / sell-to-flat / flatten), so it can be driven by the live
``AlpacaBroker`` or by an in-memory fake in tests without any network.

``AlpacaBroker`` is a stdlib-only REST client (no SDK) adapted from
``experiments/live/alpaca.py`` so this package stays self-contained — every
request is plain and auditable. Paper and live share the same API; the base URL
is chosen by :mod:`risk`, so the live endpoint is unreachable without the
explicit interlocks.
"""
from __future__ import annotations

import json
import time
import urllib.error
import urllib.request
from typing import Optional, Protocol

DATA_URL = "https://data.alpaca.markets"


class BrokerError(RuntimeError):
    pass


class Broker(Protocol):
    """Everything the trailing-stop trader needs from a broker."""

    def clock(self) -> dict: ...                 # {"is_open": bool, ...}
    def account(self) -> dict: ...               # {"equity": float, "cash": float}
    def position(self, symbol: str) -> Optional[dict]: ...  # {"qty","avg_entry_price"} or None
    def last_price(self, symbol: str) -> float: ...
    def buy(self, symbol: str, qty: int, *, extended_hours: bool = False,
            limit_price: Optional[float] = None,
            client_order_id: Optional[str] = None) -> Optional[dict]: ...
    def close(self, symbol: str) -> Optional[dict]: ...  # sell entire position
    def flatten_all(self) -> None: ...


class AlpacaBroker:
    """Live (paper or real) Alpaca REST adapter."""

    def __init__(self, base_url: str, key_id: str, secret: str):
        self.base = base_url.rstrip("/")
        self.key = key_id
        self.secret = secret
        if not (self.key and self.secret):
            raise BrokerError("ALPACA_KEY_ID / ALPACA_SECRET_KEY not set")

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
            raise BrokerError(f"{method} {url} -> {e.code}: {detail}") from None

    def _api(self, method: str, path: str, body: Optional[dict] = None):
        return self._req(method, f"{self.base}{path}", body)

    # ------------------------------------------------------------- reads
    def clock(self) -> dict:
        return self._api("GET", "/v2/clock")

    def account(self) -> dict:
        a = self._api("GET", "/v2/account")
        return {"equity": float(a["equity"]), "cash": float(a["cash"]),
                "status": a.get("status")}

    def position(self, symbol: str) -> Optional[dict]:
        try:
            p = self._api("GET", f"/v2/positions/{symbol}")
        except BrokerError as e:
            if "404" in str(e):
                return None
            raise
        return {"qty": float(p["qty"]), "avg_entry_price": float(p["avg_entry_price"])}

    def last_price(self, symbol: str) -> float:
        out = self._req("GET", f"{DATA_URL}/v2/stocks/{symbol}/trades/latest?feed=iex")
        return float(out["trade"]["p"])

    # ------------------------------------------------------------- orders
    def _submit(self, symbol: str, qty: int, side: str, *, extended_hours: bool,
                limit_price: Optional[float], client_order_id: Optional[str]) -> dict:
        body = {"symbol": symbol, "qty": str(int(qty)), "side": side,
                "time_in_force": "day", "extended_hours": bool(extended_hours)}
        if extended_hours:
            if limit_price is None:
                raise BrokerError("extended-hours orders must be limit orders")
            body.update(type="limit", limit_price=f"{limit_price:.2f}")
        elif limit_price is not None:
            body.update(type="limit", limit_price=f"{limit_price:.2f}")
        else:
            body["type"] = "market"
        if client_order_id:
            body["client_order_id"] = client_order_id[:48]
        return self._api("POST", "/v2/orders", body)

    def _await_fill(self, order_id: str, timeout_s: int = 120) -> Optional[dict]:
        deadline = time.time() + timeout_s
        while time.time() < deadline:
            o = self._api("GET", f"/v2/orders/{order_id}")
            if o["status"] == "filled":
                return {"filled_qty": float(o["filled_qty"]),
                        "fill_price": float(o["filled_avg_price"])}
            if o["status"] in ("canceled", "expired", "rejected"):
                return None
            time.sleep(2)
        try:
            self._api("DELETE", f"/v2/orders/{order_id}")
        except BrokerError:
            pass
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
            if "404" in str(e):
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
