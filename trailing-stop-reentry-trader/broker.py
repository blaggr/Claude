"""Broker interface + a thin Alpaca REST adapter for the trailing-stop trader.

The trader talks to a small ``Broker`` protocol (account / clock / position /
last price / buy / sell-to-flat / flatten), so it can be driven by the live
``AlpacaBroker`` or by an in-memory fake in tests without any network.

``AlpacaBroker`` is a stdlib-only REST client (no SDK) adapted from
``experiments/live/alpaca.py`` so this package stays self-contained — every
request is plain and auditable. Paper and live share the same API; the base URL
is chosen by :mod:`risk`. As defence in depth the live host is refused here
unless ``allow_live=True`` is passed explicitly.
"""
from __future__ import annotations

import json
import math
import time
import urllib.error
import urllib.request
from typing import Optional, Protocol
from urllib.parse import urlparse

DATA_URL = "https://data.alpaca.markets"
_LIVE_HOST = "api.alpaca.markets"          # the real-money host (paper is paper-api.alpaca.markets)
_TERMINAL = ("filled", "canceled", "expired", "rejected", "done_for_day")


class BrokerError(RuntimeError):
    def __init__(self, message: str, code: Optional[int] = None):
        super().__init__(message)
        self.code = code


class Broker(Protocol):
    """Everything the trailing-stop trader needs from a broker."""

    def clock(self) -> dict: ...
    def account(self) -> dict: ...
    def position(self, symbol: str) -> Optional[dict]: ...
    def last_price(self, symbol: str) -> float: ...
    def buy(self, symbol: str, qty: int, *, extended_hours: bool = False,
            limit_price: Optional[float] = None,
            client_order_id: Optional[str] = None) -> Optional[dict]: ...
    def close(self, symbol: str) -> Optional[dict]: ...
    def flatten_all(self) -> None: ...
    def submit_trailing_stop(self, symbol: str, qty: int, trail_price: float, *,
                             client_order_id: Optional[str] = None) -> dict: ...
    def get_order(self, order_id: str) -> Optional[dict]: ...
    def open_orders(self, symbol: str) -> list: ...
    def cancel_order(self, order_id: str) -> None: ...


def _fmt_price(p: float) -> str:
    return f"{p:.4f}" if p < 1.0 else f"{p:.2f}"


class AlpacaBroker:
    """Live (paper or real) Alpaca REST adapter."""

    def __init__(self, base_url: str, key_id: str, secret: str, *, allow_live: bool = False):
        self.base = base_url.rstrip("/")
        self.key = key_id
        self.secret = secret
        if not (self.key and self.secret):
            raise BrokerError("ALPACA_KEY_ID / ALPACA_SECRET_KEY not set")
        host = (urlparse(self.base).hostname or "").lower()   # case-insensitive, host-only
        if host == _LIVE_HOST and not allow_live:
            raise BrokerError(
                f"refusing to construct a LIVE broker for host {host} without allow_live=True")

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
        """Parse to a FINITE float, else None. Rejects None, junk, NaN and inf —
        a non-finite price/qty must never reach the strategy (it disables the
        stop: `price <= nan` is always False)."""
        try:
            f = None if v is None else float(v)
        except (TypeError, ValueError):
            return None
        return f if (f is not None and math.isfinite(f)) else None

    # ------------------------------------------------------------- reads
    def clock(self) -> dict:
        return self._api("GET", "/v2/clock")

    def account(self) -> dict:
        a = self._api("GET", "/v2/account")
        if not a:
            raise BrokerError("empty /v2/account response")
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
            if e.code == 404:
                return None
            raise
        qty, avg = self._num((p or {}).get("qty")), self._num((p or {}).get("avg_entry_price"))
        if qty is None or avg is None:
            raise BrokerError(f"position has non-numeric fields for {symbol}: {p}")
        return {"qty": qty, "avg_entry_price": avg}

    def last_price(self, symbol: str) -> float:
        out = self._req("GET", f"{DATA_URL}/v2/stocks/{symbol}/trades/latest?feed=iex")
        # `{"trade": null}` is a real payload — `.get("trade", {})` would return
        # None (key present), so guard with `or {}` before the nested .get.
        px = self._num(((out or {}).get("trade") or {}).get("p"))
        if px is None:
            raise BrokerError(f"no last price for {symbol}: {out}")
        return px

    def _safe_last(self, symbol: str) -> Optional[float]:
        try:
            return self.last_price(symbol)
        except BrokerError:
            return None

    # ------------------------------------------------------------- orders
    def _fill_from(self, o: dict, fallback_price: Optional[float]) -> Optional[dict]:
        """Build a fill dict from an order, INCLUDING partial fills. Returns None
        only when nothing filled. If a (possibly partial) fill has no average
        price yet, fall back to the supplied price so filled shares are never
        dropped from accounting. Rejects non-finite qty/price."""
        fq = self._num(o.get("filled_qty")) or 0.0
        if fq <= 0:
            return None
        avg = self._num(o.get("filled_avg_price"))
        if avg is None:
            avg = self._num(fallback_price)
        if avg is None or avg <= 0:
            return None
        return {"filled_qty": fq, "fill_price": avg}

    def _submit(self, symbol: str, qty: int, side: str, *, extended_hours: bool,
                limit_price: Optional[float], client_order_id: Optional[str]) -> dict:
        if isinstance(qty, bool) or not isinstance(qty, int) or qty < 1:
            raise BrokerError(f"invalid order qty {qty!r}: must be a whole int >= 1")
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

    def _await_fill(self, order_id: str, symbol: str, timeout_s: int = 120) -> Optional[dict]:
        """Poll until terminal, returning whatever filled (incl. partial). Follows
        a 'replaced' order to its replacement id. On timeout, cancel then poll a
        few more times so a fill that races the cancel is captured."""
        deadline = time.time() + timeout_s
        hops = 0
        while time.time() < deadline:
            o = self._api("GET", f"/v2/orders/{order_id}")
            st = o.get("status")
            if st == "replaced" and o.get("replaced_by") and hops < 5:
                order_id = o["replaced_by"]      # follow the replacement chain
                hops += 1
                continue
            if st in _TERMINAL:
                return self._fill_from(o, self._safe_last(symbol))
            time.sleep(2)
        try:
            self._api("DELETE", f"/v2/orders/{order_id}")
        except BrokerError:
            pass
        for _ in range(3):                       # cancel is async — let it settle
            try:
                o = self._api("GET", f"/v2/orders/{order_id}")
            except BrokerError:
                return None
            if o.get("status") in _TERMINAL:
                return self._fill_from(o, self._safe_last(symbol))
            time.sleep(1)
        # Never reached a terminal status — do NOT return a mid-flight partial
        # snapshot of a still-working order. The caller reconciles via position().
        return None

    def buy(self, symbol: str, qty: int, *, extended_hours: bool = False,
            limit_price: Optional[float] = None,
            client_order_id: Optional[str] = None) -> Optional[dict]:
        o = self._submit(symbol, qty, "buy", extended_hours=extended_hours,
                         limit_price=limit_price, client_order_id=client_order_id)
        return self._await_fill(o["id"], symbol)

    def close(self, symbol: str) -> Optional[dict]:
        try:
            o = self._api("DELETE", f"/v2/positions/{symbol}")
        except BrokerError as e:
            if e.code == 404:
                return None
            raise
        if o and o.get("id"):
            return self._await_fill(o["id"], symbol)
        return None

    def flatten_all(self) -> None:
        try:
            self._api("DELETE", "/v2/positions?cancel_orders=true")
        except BrokerError:
            pass

    # ----------------------------------------------------- server-side stop
    def submit_trailing_stop(self, symbol: str, qty: int, trail_price: float, *,
                             client_order_id: Optional[str] = None) -> dict:
        """Place a resting SELL trailing-stop order. The broker tracks the peak
        and triggers a market sell when price falls ``trail_price`` below it —
        so the stop survives a client crash / lag / outage. GTC so it persists
        across sessions until filled or canceled."""
        if isinstance(qty, bool) or not isinstance(qty, int) or qty < 1:
            raise BrokerError(f"invalid stop qty {qty!r}: must be a whole int >= 1")
        if not (isinstance(trail_price, (int, float)) and math.isfinite(trail_price) and trail_price > 0):
            raise BrokerError(f"invalid trail_price {trail_price!r}")
        body = {"symbol": symbol, "qty": str(int(qty)), "side": "sell",
                "type": "trailing_stop", "trail_price": _fmt_price(trail_price),
                "time_in_force": "gtc"}
        if client_order_id:
            body["client_order_id"] = client_order_id[:48]
        return self._api("POST", "/v2/orders", body)

    def get_order(self, order_id: str) -> Optional[dict]:
        try:
            return self._api("GET", f"/v2/orders/{order_id}")
        except BrokerError as e:
            if e.code == 404:
                return None
            raise

    def open_orders(self, symbol: str) -> list:
        """Open (working) orders for the symbol — used to confirm a resting stop."""
        return self._api("GET", f"/v2/orders?status=open&symbols={symbol}") or []

    def cancel_order(self, order_id: str) -> None:
        try:
            self._api("DELETE", f"/v2/orders/{order_id}")
        except BrokerError as e:
            if e.code not in (404, 422):    # already gone / not cancelable
                raise
