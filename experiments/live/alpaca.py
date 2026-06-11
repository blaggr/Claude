"""Thin Alpaca REST adapter (no SDK dependency — every request is auditable).

Paper and live share the same API; the base URL is decided by risk.resolve_mode()
so the live endpoint is unreachable without the explicit interlocks.

Endpoints used:
  GET  /v2/account                      equity, buying power, status
  GET  /v2/clock                        is_open, next_open, next_close
  POST /v2/orders                       entries and exits
  GET  /v2/orders/{id}                  fill polling
  DELETE /v2/orders/{id}                cancel unfilled
  GET  /v2/positions                    reconciliation
  DELETE /v2/positions/{symbol}         flatten one
  DELETE /v2/positions                  flatten everything (kill switch)
Market data (free IEX feed): GET data.alpaca.markets/v2/stocks/{sym}/trades/latest
"""
from __future__ import annotations

import json
import os
import time
import urllib.error
import urllib.request

DATA_URL = "https://data.alpaca.markets"


class AlpacaError(RuntimeError):
    pass


class Alpaca:
    def __init__(self, base_url: str, key_id: str | None = None, secret: str | None = None):
        self.base = base_url.rstrip("/")
        self.key = key_id or os.environ.get("ALPACA_KEY_ID", "")
        self.secret = secret or os.environ.get("ALPACA_SECRET_KEY", "")
        if not (self.key and self.secret):
            raise AlpacaError("ALPACA_KEY_ID / ALPACA_SECRET_KEY not set")

    # ------------------------------------------------------------- plumbing
    def _req(self, method: str, url: str, body: dict | None = None) -> dict | list | None:
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
            raise AlpacaError(f"{method} {url} -> {e.code}: {detail}") from None

    def _api(self, method: str, path: str, body: dict | None = None):
        return self._req(method, f"{self.base}{path}", body)

    # ------------------------------------------------------------- account
    def account(self) -> dict:
        return self._api("GET", "/v2/account")

    def equity(self) -> float:
        return float(self.account()["equity"])

    def clock(self) -> dict:
        return self._api("GET", "/v2/clock")

    def positions(self) -> list:
        return self._api("GET", "/v2/positions") or []

    # ------------------------------------------------------------- pricing
    def last_price(self, symbol: str) -> float:
        out = self._req("GET", f"{DATA_URL}/v2/stocks/{symbol}/trades/latest?feed=iex")
        return float(out["trade"]["p"])

    # -------------------------------------------------------------- orders
    def submit_order(self, symbol: str, qty: int, side: str, *, extended_hours: bool,
                     limit_price: float | None = None, client_order_id: str | None = None) -> dict:
        """Whole-share order. Extended hours requires a DAY limit order (Alpaca
        rule); during RTH we use market orders. side: 'buy' | 'sell'."""
        body = {"symbol": symbol, "qty": str(int(qty)), "side": side,
                "time_in_force": "day", "extended_hours": bool(extended_hours)}
        if extended_hours:
            if limit_price is None:
                raise AlpacaError("extended-hours orders must be limit orders")
            body.update(type="limit", limit_price=f"{limit_price:.2f}")
        elif limit_price is not None:
            body.update(type="limit", limit_price=f"{limit_price:.2f}")
        else:
            body["type"] = "market"
        if client_order_id:
            body["client_order_id"] = client_order_id[:48]
        return self._api("POST", "/v2/orders", body)

    def order(self, order_id: str) -> dict:
        return self._api("GET", f"/v2/orders/{order_id}")

    def cancel_order(self, order_id: str) -> None:
        try:
            self._api("DELETE", f"/v2/orders/{order_id}")
        except AlpacaError:
            pass  # already filled/cancelled

    def await_fill(self, order_id: str, timeout_s: int = 120) -> dict | None:
        """Poll until filled. Returns the filled order, or None after cancelling."""
        deadline = time.time() + timeout_s
        while time.time() < deadline:
            o = self.order(order_id)
            if o["status"] == "filled":
                return o
            if o["status"] in ("canceled", "expired", "rejected"):
                return None
            time.sleep(2)
        self.cancel_order(order_id)
        return None

    def close_position(self, symbol: str) -> None:
        try:
            self._api("DELETE", f"/v2/positions/{symbol}")
        except AlpacaError as e:
            if "404" not in str(e):
                raise

    def flatten_all(self) -> None:
        try:
            self._api("DELETE", "/v2/positions?cancel_orders=true")
        except AlpacaError:
            pass
